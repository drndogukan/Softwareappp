import json
import os
import re
import time
import unicodedata
from datetime import datetime
from dataclasses import dataclass


def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "topic"


def _norm_title(s: str) -> str:
    s = (s or "").strip().lower()
    # Diacritics-insensitive compare (Koşullar == Kosullar)
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = re.sub(r"\s+", " ", s)
    return s


def norm_prompt(s: str) -> str:
    """
    Normalize a question prompt for cross-topic/language de-duplication.
    Keep it conservative: whitespace + case folding only.
    """
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _merge_unique_by_id(items):
    """Merge list[dict] by 'id' (keep first)."""
    out = []
    seen = set()
    for it in items or []:
        if not isinstance(it, dict):
            continue
        iid = str(it.get("id", "") or "")
        if not iid:
            out.append(it)
            continue
        if iid in seen:
            continue
        seen.add(iid)
        out.append(it)
    return out


def dedupe_topics(catalog: dict) -> int:
    """
    Remove duplicate topics per language by:
    - same topic id (exact)
    - same normalized title (case/diacritics/whitespace-insensitive)
    When merging duplicates, keep the richest content and union questions/challenges by id.
    Returns number of topics removed.
    """
    removed = 0
    for lang in catalog.get("languages", []):
        topics = list(lang.get("topics") or [])

        # (1) Merge duplicates by id
        merged_by_id = []
        by_id = {}
        for t in topics:
            if not isinstance(t, dict):
                continue
            tid = str(t.get("id", "") or "").strip()
            if not tid:
                merged_by_id.append(t)
                continue
            if tid not in by_id:
                by_id[tid] = t
                merged_by_id.append(t)
                continue

            base = by_id[tid]
            # Prefer longer markdown
            if len((t.get("contentMarkdown") or "")) > len((base.get("contentMarkdown") or "")):
                base["contentMarkdown"] = t.get("contentMarkdown") or base.get("contentMarkdown")
            # Prefer a non-empty title
            if not (base.get("title") or "").strip() and (t.get("title") or "").strip():
                base["title"] = t.get("title")
            base["questions"] = _merge_unique_by_id((base.get("questions") or []) + (t.get("questions") or []))
            base["compilerChallenges"] = _merge_unique_by_id(
                (base.get("compilerChallenges") or []) + (t.get("compilerChallenges") or [])
            )
            removed += 1

        # (2) Merge duplicates by normalized title (different ids but same title)
        final = []
        by_title = {}
        for t in merged_by_id:
            if not isinstance(t, dict):
                continue
            key = _norm_title(t.get("title") or "")
            if not key:
                final.append(t)
                continue
            if key not in by_title:
                by_title[key] = t
                final.append(t)
                continue

            base = by_title[key]
            if len((t.get("contentMarkdown") or "")) > len((base.get("contentMarkdown") or "")):
                base["contentMarkdown"] = t.get("contentMarkdown") or base.get("contentMarkdown")
            base["questions"] = _merge_unique_by_id((base.get("questions") or []) + (t.get("questions") or []))
            base["compilerChallenges"] = _merge_unique_by_id(
                (base.get("compilerChallenges") or []) + (t.get("compilerChallenges") or [])
            )
            removed += 1

        lang["topics"] = final

    return removed


def next_id(existing: set[str], prefix: str) -> str:
    i = 1
    while True:
        cand = f"{prefix}{i}"
        if cand not in existing:
            existing.add(cand)
            return cand
        i += 1


STOPWORDS_TR = {
    "ve", "ile", "icin", "için", "bu", "bir", "the", "to", "of", "a", "an",
    "konu", "konular", "hedef", "mini", "alistirma", "alıştırma", "giris", "giriş",
    "temel", "ileri", "uzmanliga", "uzmanlığa", "gecis", "geçiş", "not",
}


def extract_keywords(md: str, title: str) -> list[str]:
    """
    Extract a few topic-specific keywords from markdown headings/bullets + title.
    Offline heuristic: keep short, distinct, non-stopword tokens.
    """
    text = f"{title}\n{md or ''}"
    text = text.lower()
    # keep letters (turkish included) + digits
    tokens = re.findall(r"[a-z0-9çğıöşü]+", text)
    # prefer "code-ish" keywords
    prefer = {
        "if", "else", "switch", "for", "while", "class", "struct", "interface",
        "pointer", "malloc", "free", "oop", "inheritance", "polymorphism",
        "async", "await", "promise", "future", "goroutine", "channel",
        "ownership", "borrow", "lifetime", "trait", "vector", "map", "set", "list",
        "select", "where", "join", "index", "transaction", "window",
        "null", "nullable", "generic", "template", "stl", "stream", "collections",
        "protocol", "extension", "closure", "scope",
    }
    out: list[str] = []
    seen = set()
    for t in tokens:
        if len(t) < 3:
            continue
        if t in STOPWORDS_TR:
            continue
        if t in seen:
            continue
        # boost preferred tokens first
        if t in prefer:
            out.append(t)
            seen.add(t)
            if len(out) >= 6:
                return out
    # then fill with frequent-ish tokens (first-appearance is enough here)
    for t in tokens:
        if len(t) < 4:
            continue
        if t in STOPWORDS_TR or t in seen:
            continue
        if t.isdigit():
            continue
        out.append(t)
        seen.add(t)
        if len(out) >= 6:
            break
    return out


def topic_flags(md: str, title: str) -> dict[str, bool]:
    text = f"{title}\n{md or ''}".lower()
    def has(*parts: str) -> bool:
        return any(p in text for p in parts)
    return {
        "loop": has("döng", "dongu", "for", "while"),
        "cond": has("if", "else", "switch", "koşul", "kosul"),
        "func": has("fonksiyon", "function", "def", "lambda", "arrow"),
        "oop": has("oop", "class", "struct", "interface", "protocol", "inherit", "mixin"),
        "async": has("async", "await", "promise", "future", "goroutine", "channel", "concurrency"),
        "collections": has("list", "array", "dict", "map", "set", "vector", "hashmap", "collection", "stl"),
        "memory": has("pointer", "malloc", "free", "heap", "stack", "raii"),
        "sql": has("sql", "select", "where", "join", "index", "transaction", "window"),
        "null": has("null", "nullable", "null safety", "optional"),
    }


def make_teaching_markdown(lang_id: str, lang_name: str, topic_title: str, topic_id: str, md: str) -> str:
    """
    Produce a detailed, readable teaching note in Turkish.
    We keep it offline-friendly and deterministic.
    """
    lid = (lang_id or "").strip().lower()
    ln = (lang_name or lang_id).strip() or lid
    tt = (topic_title or topic_id).strip() or "Konu"
    kws = extract_keywords(md or "", tt)
    flags = topic_flags(md or "", tt)

    def code(lang: str, s: str) -> str:
        return f"\n```{lang}\n{s.strip()}\n```\n"

    def section(title: str, body: str) -> str:
        return f"\n### {title}\n{body.strip()}\n"

    # Topic category heuristics
    t = f"{tt}\n{md}".lower()
    is_types = any(x in t for x in ["veri tip", "tip", "types", "tür", "tur", "null", "optional"])
    is_flow = any(x in t for x in ["if", "else", "switch", "koşul", "kosul", "döng", "dongu", "for", "while"])
    is_funcs = any(x in t for x in ["fonksiyon", "function", "def", "lambda", "arrow", "parametre", "return"])
    is_collections = any(x in t for x in ["list", "array", "dict", "map", "set", "vector", "slice", "hashmap", "collection"])
    is_oop = any(x in t for x in ["oop", "class", "struct", "interface", "inherit", "mixin", "protocol", "extension"])
    is_async = any(x in t for x in ["async", "await", "promise", "future", "goroutine", "channel", "concurrency"])
    is_sql = any(x in t for x in ["sql", "select", "where", "join", "index", "transaction", "window"])
    is_memory = any(x in t for x in ["pointer", "malloc", "free", "heap", "stack", "raii", "ownership", "borrow"])

    # Language snippets
    if lid == "python":
        ex_types = code("python", "x = 10      # int\npi = 3.14   # float\nname = 'Ada'# str\nok = True   # bool")
        ex_flow = code("python", "x = 10\nif x > 5:\n    print('buyuk')\nelse:\n    print('kucuk')\n\nfor i in range(3):\n    print(i)")
        ex_funcs = code("python", "def add(a, b):\n    return a + b\n\nprint(add(2, 3))")
        ex_col = code("python", "nums = [1,2,3]\nnums.append(4)\n\nfreq = {}\nfor w in ['a','b','a']:\n    freq[w] = freq.get(w, 0) + 1\nprint(freq)")
        ex_oop = code("python", "class Student:\n    def __init__(self, name, grade):\n        self.name = name\n        self.grade = grade\n\ns = Student('Ada', 100)\nprint(s.name)")
        ex_async = code("python", "import asyncio\n\nasync def main():\n    await asyncio.sleep(0.1)\n    print('done')\n\nasyncio.run(main())")
        # richer examples
        ex_types_2 = code("python", "age = int('42')\nratio = float('3.5')\nprint(age, ratio)")
        ex_flow_2 = code("python", "total = 0\nfor n in range(1, 6):\n    total += n\nprint(total)  # 15")
        ex_funcs_2 = code("python", "def is_even(n: int) -> bool:\n    return n % 2 == 0\n\nprint(is_even(4))")
        ex_col_2 = code("python", "nums = [1,2,3,4,5]\nevens = [n for n in nums if n % 2 == 0]\nprint(evens)")
        ex_oop_2 = code("python", "class Animal:\n    def speak(self):\n        return '...'\n\nclass Dog(Animal):\n    def speak(self):\n        return 'hav'\n\nprint(Dog().speak())")
        ex_async_2 = code("python", "import asyncio\n\nasync def job(i):\n    await asyncio.sleep(0.05)\n    return i * 2\n\nasync def main():\n    results = await asyncio.gather(job(1), job(2), job(3))\n    print(results)\n\nasyncio.run(main())")
        lang = "python"
    elif lid in ("javascript", "typescript"):
        ex_types = code("js", "let x = 10;        // number\nconst name = 'Ada'; // string\nconst ok = true;    // boolean")
        ex_flow = code("js", "const x = 10;\nif (x > 5) console.log('buyuk');\n\nfor (let i=0;i<3;i++) console.log(i);")
        ex_funcs = code("js", "function add(a,b){ return a+b; }\nconst add2 = (a,b) => a+b;\nconsole.log(add2(2,3));")
        ex_col = code("js", "const nums = [1,2,3];\nconst doubled = nums.map(n => n*2);\nconst sum = nums.reduce((a,b)=>a+b, 0);\nconsole.log(doubled, sum);")
        ex_oop = code("js", "class Student {\n  constructor(name, grade){ this.name=name; this.grade=grade; }\n}\nconsole.log(new Student('Ada', 100));")
        ex_async = code("js", "async function main(){\n  await Promise.resolve();\n  console.log('done');\n}\nmain();")
        ex_types_2 = code("js", "console.log(Number('42') + 1); // 43\nconsole.log(String(10)); // '10'")
        ex_flow_2 = code("js", "let total = 0;\nfor (let n=1;n<=5;n++) total += n;\nconsole.log(total); // 15")
        ex_funcs_2 = code("js", "const isEven = (n) => n % 2 === 0;\nconsole.log(isEven(4));")
        ex_col_2 = code("js", "const nums = [1,2,3,4,5];\nconst evens = nums.filter(n => n%2===0);\nconsole.log(evens);")
        ex_oop_2 = code("js", "class Animal { speak(){ return '...'; } }\nclass Dog extends Animal { speak(){ return 'hav'; } }\nconsole.log(new Dog().speak());")
        ex_async_2 = code("js", "const job = async (i) => i*2;\n(async () => {\n  const results = await Promise.all([job(1), job(2), job(3)]);\n  console.log(results);\n})();")
        lang = "js"
    elif lid == "dart":
        ex_types = code("dart", "final int x = 10;\nfinal double pi = 3.14;\nfinal String name = 'Ada';\nfinal bool ok = true;")
        ex_flow = code("dart", "final x = 10;\nif (x > 5) {\n  print('buyuk');\n} else {\n  print('kucuk');\n}\nfor (var i=0;i<3;i++) {\n  print(i);\n}")
        ex_funcs = code("dart", "int add(int a, int b) => a + b;\nvoid main(){\n  print(add(2,3));\n}")
        ex_col = code("dart", "final nums = [1,2,3];\nfinal doubled = nums.map((n)=>n*2).toList();\nprint(doubled);")
        ex_oop = code("dart", "class Student {\n  final String name;\n  final int grade;\n  Student(this.name, this.grade);\n}\nvoid main(){\n  print(Student('Ada', 100).name);\n}")
        ex_async = code("dart", "Future<void> main() async {\n  await Future.delayed(const Duration(milliseconds: 100));\n  print('done');\n}")
        ex_types_2 = code("dart", "final n = int.parse('42');\nfinal d = double.parse('3.5');\nprint('$n $d');")
        ex_flow_2 = code("dart", "var total = 0;\nfor (var n=1; n<=5; n++) total += n;\nprint(total); // 15")
        ex_funcs_2 = code("dart", "bool isEven(int n) => n % 2 == 0;\nvoid main(){\n  print(isEven(4));\n}")
        ex_col_2 = code("dart", "final nums = [1,2,3,4,5];\nfinal evens = nums.where((n)=>n.isEven).toList();\nprint(evens);")
        ex_oop_2 = code("dart", "abstract class Animal { String speak(); }\nclass Dog implements Animal { @override String speak() => 'hav'; }\nvoid main(){ print(Dog().speak()); }")
        ex_async_2 = code("dart", "Future<int> job(int i) async => i*2;\nFuture<void> main() async {\n  final results = await Future.wait([job(1), job(2), job(3)]);\n  print(results);\n}")
        lang = "dart"
    elif lid in ("c", "cpp"):
        ex_types = code("c", "int x = 10;\nfloat pi = 3.14f;\nchar c = 'A';\nchar name[] = \"Ada\";")
        ex_flow = code("c", "int x = 10;\nif (x > 5) {\n  printf(\"buyuk\\n\");\n}\nfor (int i=0;i<3;i++) {\n  printf(\"%d\\n\", i);\n}")
        ex_funcs = code("c", "int add(int a, int b){ return a+b; }\nint main(){\n  printf(\"%d\\n\", add(2,3));\n  return 0;\n}")
        ex_col = code("c", "int a[3] = {1,2,3};\nint sum = 0;\nfor(int i=0;i<3;i++) sum += a[i];\nprintf(\"%d\\n\", sum);")
        ex_oop = ""
        ex_async = ""
        ex_types_2 = code("c", "int age = atoi(\"42\");\nprintf(\"%d\\n\", age);")
        ex_flow_2 = code("c", "int total = 0;\nfor (int n=1;n<=5;n++) total += n;\nprintf(\"%d\\n\", total);")
        ex_funcs_2 = code("c", "int is_even(int n){ return n % 2 == 0; }\nprintf(\"%d\\n\", is_even(4));")
        ex_col_2 = code("c", "char s[] = \"Ada\";\nprintf(\"%s\\n\", s);")
        lang = "c"
    elif lid == "sql":
        ex_types = ""
        ex_flow = ""
        ex_funcs = ""
        ex_col = ""
        ex_oop = ""
        ex_async = ""
        lang = "sql"
    else:
        ex_types = code("", "// Örnek kod bu dil için eklenebilir.")
        ex_flow = ""
        ex_funcs = ""
        ex_col = ""
        ex_oop = ""
        ex_async = ""
        lang = ""

    # Build teaching note (auto marker so we can safely regenerate later)
    marker = "<!-- AUTO_TEACHING_NOTE v2 -->"
    intro = (
        f"{marker}\n"
        f"Bu sayfa **{ln}** dilinde **{tt}** konusunu yazılı şekilde öğretir.\n"
        f"Videoyu izleyemeyenler veya hızlı tekrar isteyenler için; kavramlar, örnekler, sık hatalar ve alıştırmalar burada.\n"
    )
    out = f"### Konu: {tt}\n{intro}\n"

    out += section(
        "Bu konuyu nerede kullanırsın?",
        "- Gerçek projelerde bu konu sürekli karşına çıkar.\n"
        "- Amaç sadece ezber değil: **neden** böyle kullanıldığını anlamak.\n"
        "- Bu sayfanın sonunda mini alıştırmalarla kendini test edebilirsin.\n",
    )

    if kws:
        out += section(
            "Anahtar kelimeler",
            "Bu konuyu okurken aşağıdaki kavramlar özellikle önemlidir:\n- "
            + "\n- ".join(kws[:8]),
        )

    # Explain based on category
    if is_sql:
        out += section(
            "Özet",
            "- SQL'de veri tablo(lar) üzerinden sorgulanır.\n"
            "- Temel yapı: `SELECT ... FROM ...` ve filtreleme için `WHERE`.\n"
            "- Çok tablo için `JOIN` kullanılır; performans için `INDEX` kritiktir.\n",
        )
        out += section(
            "Temel sözdizimi",
            "Aşağıdaki örnekler genel SQL mantığını gösterir. Burada amaç; SELECT/WHERE/JOIN düşünce şeklini oturtmaktır.",
        )
        out += code("sql", "SELECT *\nFROM table_name\nWHERE id = 5\nORDER BY created_at DESC\nLIMIT 10;")
        out += code("sql", "SELECT a.id, b.name\nFROM a\nINNER JOIN b ON b.a_id = a.id;")
        out += code("sql", "SELECT category, COUNT(*) AS cnt\nFROM table_name\nGROUP BY category\nORDER BY cnt DESC;")
        out += section(
            "Adım adım düşünme",
            "1) Hangi tablo(lar)dan veri çekiyorsun?\n"
            "2) Hangi kolonlara ihtiyacın var?\n"
            "3) Filtre (WHERE) ne olmalı?\n"
            "4) Sıralama (ORDER BY) ve limit gerekli mi?\n"
            "5) JOIN gerekiyorsa anahtar kolonlar doğru mu?\n",
        )
        out += section(
            "Sık hatalar",
            "- `JOIN` koşulunu yanlış yazmak (kartesyen çarpım).\n- Index olmadan büyük tabloda yavaş sorgu.\n- NULL karşılaştırmasını `=` ile yapmak (çoğu durumda `IS NULL`).",
        )
        out += section(
            "İpuçları",
            "- Sorguyu önce küçük yaz, sonra genişlet.\n"
            "- Büyük tabloda önce WHERE ile daralt.\n"
            "- Performans için `EXPLAIN`/query plan okumayı alışkanlık yap.\n",
        )
        out += section(
            "Mini alıştırmalar",
            "- id=10 olan kaydı çek.\n- 2 tabloyu INNER JOIN ile birleştir.\n- Son 20 kaydı tarih sıralı getir.",
        )
        return out.strip() + "\n"

    if is_types:
        out += section(
            "Temel kavramlar",
            "- **int**: tam sayılar\n- **float/double**: ondalıklı sayılar\n- **string/str**: metin\n- **bool**: true/false\n"
            "- Tip dönüşümleri (casting) ve null/optional mantığı (varsa) önemlidir.",
        )
        out += section(
            "Neden önemlidir?",
            "Veri tipi, bir değerin **ne olduğunu** (sayı mı, metin mi?) ve üzerinde hangi işlemlerin güvenli olduğunu belirler.\n"
            "Yanlış tip kullanımı; hata, beklenmeyen sonuç veya performans sorununa yol açabilir.\n",
        )
        out += section(
            "Örnekler",
            "Aşağıdaki örnekleri okuyup satır satır anlamaya çalış.\n" + (ex_types or ""),
        )
        if 'ex_types_2' in locals():
            out += section("Dönüşüm örneği", ex_types_2)
        out += section(
            "Tip dönüşümü (casting) mantığı",
            "- Bazı diller otomatik dönüştürür, bazıları hata verir.\n"
            "- Kural: Dönüşüm yaparken **ne kaybediyorum?** (ondalık, büyük sayı, karakter kodu) diye düşün.\n",
        )
        out += section(
            "Dikkat edilmesi gerekenler",
            "- Sayı + metin işlemleri (bazı dillerde hata verir).\n"
            "- Karşılaştırmalarda tip uyumu.\n"
            "- Null/optional varsa: önce kontrol et, sonra kullan.",
        )
        out += section(
            "Sık yapılan hatalar",
            "- `'10' + 2` gibi ifadelerde sonuç beklenenden farklı çıkabilir.\n"
            "- `float` ile eşitlik karşılaştırması (0.1 + 0.2 gibi).\n"
            "- Null değeri kontrol etmeden kullanmak.\n",
        )
        out += section(
            "Mini alıştırmalar",
            "- 2 değişken tanımla (int ve string) ve ekrana yazdır.\n"
            "- Ondalıklı bir sayı üret ve yuvarlama dene.\n"
            "- Metinden sayıya dönüşüm yap (ör. '42' → 42).\n"
            "- Nullable bir değer için güvenli kontrol yap (varsa).\n",
        )
        return out.strip() + "\n"

    if is_flow:
        out += section(
            "Temel kavramlar",
            "- Koşullar: `if/else` (ve varsa `switch`)\n- Döngüler: `for/while`\n- `break/continue` ile akış kontrolü",
        )
        out += section(
            "Ne işe yarar?",
            "Koşullar ve döngüler, programın **karar vermesini** ve **tekrarlı işleri** otomatik yapmasını sağlar.\n"
            "Bu konu; algoritma kurmanın temelidir.\n",
        )
        out += section("Örnekler", ex_flow or "")
        if 'ex_flow_2' in locals():
            out += section("Ek örnek: Toplam hesaplama", ex_flow_2)
        out += section(
            "Adım adım strateji",
            "- Önce problemi küçük parçalara böl.\n"
            "- Döngü kaç kere dönecek? (başlangıç, bitiş, adım)\n"
            "- Koşul doğru/yanlış olunca ne yapacaksın?\n",
        )
        out += section(
            "Sık hatalar",
            "- Döngü şartını yanlış kurmak (sonsuz döngü).\n- Off-by-one (0..n-1 vs 1..n).\n- if koşulunda atama/karşılaştırmayı karıştırmak (dile göre).",
        )
        out += section(
            "İpuçları",
            "- Döngü içinde debug için küçük print/log eklemek çok faydalıdır.\n"
            "- Sınır değerleri (0, 1, n-1, n) mutlaka dene.\n",
        )
        out += section(
            "Mini alıştırmalar",
            "- 1..50 arası 3'e bölünenleri yazdır.\n- Bir sayı asal mı kontrol et.\n- Basit bir menü (switch/if) yaz.",
        )
        return out.strip() + "\n"

    if is_funcs:
        out += section(
            "Temel kavramlar",
            "- Fonksiyon: tekrar kullanılan kod bloğu\n- Parametre ve `return`\n- Varsayılan parametre/named parametre (dile göre)\n",
        )
        out += section(
            "Neden fonksiyon kullanırız?",
            "- Kodu tekrar etmemek (DRY)\n- Okunabilirlik\n- Test edilebilirlik\n- Hata ayıklamayı kolaylaştırmak\n",
        )
        out += section("Örnekler", ex_funcs or "")
        if 'ex_funcs_2' in locals():
            out += section("Ek örnek: boolean fonksiyon", ex_funcs_2)
        out += section(
            "İyi pratikler",
            "- Fonksiyon tek sorumluluk taşısın.\n- İsimler anlamlı olsun.\n- Parametre sayısını makul tut.\n",
        )
        out += section(
            "Sık hatalar",
            "- return unutmak.\n- Parametre sırasını karıştırmak.\n- Global değişkenlere aşırı bağımlılık.",
        )
        out += section(
            "Mini alıştırmalar",
            "- `add(a,b)` yaz.\n- `isEven(n)` yaz.\n- Bir listeyi alan ve ortalamasını döndüren fonksiyon yaz.",
        )
        return out.strip() + "\n"

    if is_collections:
        out += section(
            "Temel kavramlar",
            "- Koleksiyonlar: liste/dizi, sözlük/map, set\n- Amaç: çoklu veriyi düzenli yönetmek\n",
        )
        out += section(
            "Ne zaman hangisini kullanırsın?",
            "- **List/Array**: sıralı veri, index ile erişim\n"
            "- **Map/Dict**: anahtar → değer eşlemesi\n"
            "- **Set**: benzersiz elemanlar\n",
        )
        out += section("Örnekler", ex_col or "")
        if 'ex_col_2' in locals():
            out += section("Ek örnek: Filtreleme", ex_col_2)
        out += section(
            "Sık hatalar",
            "- Index taşması.\n- Map'te anahtar yokken direkt erişim.\n- Mutability/immutability farkını karıştırmak.",
        )
        out += section(
            "İpuçları",
            "- Önce veri yapısını seç, sonra algoritmayı yaz.\n- Büyük listelerde gereksiz kopyalardan kaçın.\n",
        )
        out += section(
            "Mini alıştırmalar",
            "- Kelime frekansı çıkar.\n- Listeyi filtrele.\n- En büyük elemanı bul.",
        )
        return out.strip() + "\n"

    if is_oop:
        out += section(
            "Temel kavramlar",
            "- class/struct: veri + davranış\n- encapsulation (private/public)\n- inheritance/polymorphism (varsa)\n",
        )
        if ex_oop:
            out += section("Örnek", ex_oop)
        if 'ex_oop_2' in locals():
            out += section("Ek örnek: kalıtım/implement", ex_oop_2)
        out += section(
            "Ne zaman OOP?",
            "- Gerçek dünyadaki nesneleri modellemek için.\n- Kod büyüdükçe sorumlulukları bölmek için.\n",
        )
        out += section(
            "Sık hatalar",
            "- Her şeyi class yapmak (gereksiz karmaşıklık).\n- Sorumlulukları tek sınıfta toplamak.\n- Yanlış erişim seviyeleri.",
        )
        out += section(
            "İpuçları",
            "- Önce basit başla, ihtiyaç oldukça soyutla.\n- Büyük sınıfları parçalara ayır.\n",
        )
        out += section(
            "Mini alıştırmalar",
            "- `Student(name, grade)` modeli oluştur.\n- İki sınıf arasında ilişki kur.\n- Basit bir interface/protocol tasarla.",
        )
        return out.strip() + "\n"

    if is_async:
        out += section(
            "Temel kavramlar",
            "- Asenkron: işi beklemeden akışı sürdürmek\n- `async/await` ile okunabilir asenkron kod\n- Hata yönetimi çok önemlidir\n",
        )
        if ex_async:
            out += section("Örnek", ex_async)
        if 'ex_async_2' in locals():
            out += section("Ek örnek: paralel işler", ex_async_2)
        out += section(
            "Ne zaman asenkron?",
            "- Ağ istekleri (HTTP)\n- Dosya okuma/yazma\n- Zaman alan işlemler\n\nAmaç: UI donmasın, uygulama akıcı kalsın.\n",
        )
        out += section(
            "Sık hatalar",
            "- await unutmak.\n- Hataları yakalamamak.\n- Paylaşılan state'i eşzamanlı değiştirip yarış durumu oluşturmak.",
        )
        out += section(
            "İpuçları",
            "- Her async işin hata senaryosunu düşün.\n- Timeout ve iptal (cancel) mantığını öğren.\n",
        )
        out += section(
            "Mini alıştırmalar",
            "- 100ms bekleyip çıktı veren async fonksiyon yaz.\n- 2 async işi sırayla ve paralel çalıştırmayı dene.\n- Hata fırlatan async fonksiyonu try/catch ile yakala.",
        )
        return out.strip() + "\n"

    if is_memory:
        out += section(
            "Temel kavramlar",
            "- Bellek: stack/heap\n- Pointer/ownership gibi kavramlar (dile göre)\n- Kaynak yönetimi: sızıntı ve yaşam süresi\n",
        )
        out += section(
            "Neden kritik?",
            "Bellek hataları; çökme, güvenlik açığı veya yanlış sonuçlara yol açabilir.\n"
            "Bu yüzden bu konu, özellikle sistem dillerinde uzmanlığa giden yoldur.\n",
        )
        out += section(
            "Sık hatalar",
            "- Serbest bırakılmış belleği kullanmak.\n- Null pointer dereference.\n- Yanlış kopyalama/taşıma (dile göre).",
        )
        out += section(
            "İpuçları",
            "- Kaynağı kim açtıysa o kapatsın.\n- Yaşam süresini (lifetime) çizerek düşün.\n",
        )
        out += section(
            "Mini alıştırmalar",
            "- Dinamik bir dizi ayırıp doldur.\n"
            "- Bir kaynağı aç/kapat akışını güvenli yap.\n"
            "- Kasıtlı null/boş değer hatası yapıp nasıl önleneceğini yaz.\n",
        )
        return out.strip() + "\n"

    # Generic fallback (still teaching)
    kw_line = ", ".join(kws[:5]) if kws else "—"
    out += section(
        "Bu konudan beklenen",
        f"- Konunun ana fikrini anlayabilmek\n- Küçük örneklerle pratik yapabilmek\n- Test/Compiler sorularıyla pekiştirebilmek\n\n**Anahtar kelimeler**: {kw_line}",
    )
    out += section(
        "Mini alıştırmalar",
        "- Konuyu 3 maddeyle özetle.\n- 1 küçük örnek yaz.\n- 3 soru üretip kendin cevapla.",
    )
    return out.strip() + "\n"


def ensure_curriculum(catalog: dict) -> int:
    """
    Ensure each language has a full beginner->advanced topic set.
    Adds missing topics with minimal placeholder markdown (will be expanded later).
    Returns number of topics added.
    """
    curriculum: dict[str, list[tuple[str, str, str]]] = {
        # (id, title, seed_markdown)
        "c": [
            ("c-giris", "Giriş ve Kurulum", "### Hedef\n- C diline giriş\n- Derleyici kurulumu\n"),
            ("c-degiskenler", "Değişkenler ve Temel Tipler", "### Konular\n- int/char/float/double\n- sizeof\n"),
            ("c-operatorler", "Operatörler", "### Konular\n- aritmetik\n- karşılaştırma\n- mantıksal\n"),
            ("c-kontrol-akisi", "Koşullar ve Döngüler", "### Konular\n- if/switch\n- for/while\n"),
            ("c-fonksiyonlar", "Fonksiyonlar", "### Konular\n- prototip\n- parametre/return\n"),
            ("c-array-string", "Array ve String", "### Konular\n- diziler\n- char dizileri\n"),
            ("c-pointer-bellek", "Pointer ve Bellek Yönetimi", "### Konular\n- pointer\n- malloc/free\n"),
            ("c-struct", "Struct ve Enum", "### Konular\n- struct\n- enum\n"),
            ("c-dosya", "Dosya İşlemleri", "### Konular\n- fopen/fgets/fprintf\n"),
            ("c-debug-perf", "Debug ve Performans", "### Konular\n- gdb\n- valgrind\n"),
        ],
        "python": [
            ("py-kurulum", "Kurulum ve İlk Program", "### Konular\n- python kurulumu\n- print\n"),
            ("py-degiskenler", "Değişkenler ve Veri Tipleri", "### Konular\n- int/float/str/bool\n"),
            ("py-kosul-dongu", "Koşullar ve Döngüler", "### Konular\n- if/elif/else\n- for/while\n"),
            ("py-fonksiyonlar", "Fonksiyonlar", "### Konular\n- def\n- return\n"),
            ("py-koleksiyonlar", "List / Dict / Set / Tuple", "### Konular\n- list\n- dict\n- set\n- tuple\n"),
            ("py-string", "String İşlemleri", "### Konular\n- slicing\n- format\n"),
            ("py-dosya", "Dosya Okuma/Yazma", "### Konular\n- open\n- read/write\n"),
            ("py-hatalar", "Hata Yönetimi", "### Konular\n- try/except\n"),
            ("py-oop", "Nesne Yönelimli Programlama", "### Konular\n- class\n- inheritance\n"),
            ("py-ileri", "İleri Seviye: Paketler, Test, Async", "### Konular\n- venv\n- pytest\n- asyncio\n"),
        ],
        "javascript": [
            ("js-giris", "Giriş ve Temel Sözdizimi", "### Konular\n- let/const\n- fonksiyon\n"),
            ("js-tipler", "Tipler ve Operatörler", "### Konular\n- number/string/bool\n- ===\n"),
            ("js-kontrol", "Koşullar ve Döngüler", "### Konular\n- if/switch\n- for/while\n"),
            ("js-fonksiyon", "Fonksiyonlar ve Scope/Closure", "### Konular\n- scope\n- closure\n"),
            ("js-obj-array", "Array ve Object", "### Konular\n- map/filter/reduce\n"),
            ("js-dom", "DOM (Tarayıcı) Temelleri", "### Konular\n- querySelector\n- events\n"),
            ("js-async", "Async: Promise ve async/await", "### Konular\n- promise\n- await\n"),
            ("js-moduller", "Modüller ve Tooling", "### Konular\n- import/export\n- npm\n"),
            ("js-test", "Test ve Best Practices", "### Konular\n- test yaklaşımı\n"),
            ("js-proje", "Mini Proje", "### Hedef\n- öğrendiklerini birleştir\n"),
        ],
        "typescript": [
            ("ts-giris", "Giriş: TypeScript Nedir?", "### Konular\n- TS vs JS\n"),
            ("ts-tip-sistemi", "Tip Sistemi ve Interface", "### Konular\n- type/interface\n"),
            ("ts-union", "Union, Narrowing", "### Konular\n- union\n- narrowing\n"),
            ("ts-generics", "Generics", "### Konular\n- generic fonksiyon\n"),
            ("ts-moduller", "Modüller ve Tooling", "### Konular\n- tsconfig\n"),
            ("ts-uzmanliga-gecis", "Uzmanlığa Geçiş", "### Konular\n- build/test/lint\n"),
        ],
        "java": [
            ("java-giris", "Giriş ve Kurulum", "### Konular\n- JVM\n- main\n"),
            ("java-degiskenler", "Değişkenler ve Temel Türler", "### Konular\n- int/double/String\n"),
            ("java-kontrol-akisi", "Koşullar ve Döngüler", "### Konular\n- if/switch\n- for/while\n"),
            ("java-oop", "OOP: Class, Interface, Inheritance", "### Konular\n- class\n- interface\n"),
            ("java-collections", "Collections Framework", "### Konular\n- List/Map/Set\n"),
            ("java-streams", "Stream API", "### Konular\n- map/filter\n"),
            ("java-exceptions", "Exception ve Hata Yönetimi", "### Konular\n- try/catch\n"),
            ("java-concurrency", "Concurrency (Temel)", "### Konular\n- thread\n- executor\n"),
            ("java-test", "Test Yaklaşımı (JUnit)", "### Konular\n- unit test\n"),
        ],
        "dart": [
            ("dart-giris", "Giriş ve Kurulum", "### Konular\n- Dart\n- main\n"),
            ("dart-degiskenler", "Değişkenler, Tipler, Null Safety", "### Konular\n- var/final/const\n- null safety\n"),
            ("dart-kontrol-akisi", "Kontrol Akışı", "### Konular\n- if/switch\n- for/while\n"),
            ("dart-fonksiyonlar", "Fonksiyonlar ve Named Params", "### Konular\n- functions\n"),
            ("dart-collections", "List/Map ve Koleksiyonlar", "### Konular\n- list/map\n"),
            ("dart-async", "Async: Future/Stream", "### Konular\n- async/await\n- stream\n"),
            ("dart-oop", "OOP ve Mixin", "### Konular\n- class\n- mixin\n"),
            ("dart-test", "Test Yaklaşımı", "### Konular\n- unit/widget test\n"),
        ],
        "swift": [
            ("swift-giris", "Giriş ve Temeller", "### Konular\n- let/var\n"),
            ("swift-temeller", "Temeller: Değişkenler ve Tipler", "### Konular\n- Int/Double/String\n- Optional\n"),
            ("swift-kontrol-akisi", "Kontrol Akışı", "### Konular\n- if/switch\n- for\n"),
            ("swift-fonksiyon", "Fonksiyonlar ve Closure", "### Konular\n- closure\n"),
            ("swift-struct-class", "Struct vs Class", "### Konular\n- value/reference\n"),
            ("swift-protokoller", "Protocol ve Extensions", "### Konular\n- protocol\n- extension\n"),
            ("swift-async", "Concurrency (async/await)", "### Konular\n- async/await\n"),
            ("swift-test", "Test (XCTest) Yaklaşımı", "### Konular\n- unit test\n"),
        ],
        "kotlin": [
            ("kotlin-giris", "Giriş", "### Konular\n- JVM\n- main\n"),
            ("kotlin-temeller", "Temeller: Değişkenler ve Null Safety", "### Konular\n- val/var\n- nullable\n"),
            ("kotlin-fonksiyon", "Fonksiyonlar ve Lambda", "### Konular\n- lambda\n"),
            ("kotlin-collections", "Collections", "### Konular\n- map/filter\n"),
            ("kotlin-oop", "OOP ve Sealed Class", "### Konular\n- sealed\n"),
            ("kotlin-coroutines", "Coroutines", "### Konular\n- suspend\n"),
            ("kotlin-test", "Test Yaklaşımı", "### Konular\n- unit test\n"),
        ],
        "php": [
            ("php-giris", "Giriş", "### Konular\n- echo\n"),
            ("php-syntax", "Temel Sözdizimi", "### Konular\n- değişken\n- array\n"),
            ("php-fonksiyon", "Fonksiyonlar", "### Konular\n- function\n"),
            ("php-oop", "OOP", "### Konular\n- class\n"),
            ("php-web", "Web: HTTP ve Form", "### Konular\n- GET/POST\n"),
            ("php-guvenlik", "Güvenlik Temelleri", "### Konular\n- validation\n"),
            ("php-composer", "Composer ve Paketler", "### Konular\n- composer\n"),
        ],
        "ruby": [
            ("ruby-giris", "Giriş", "### Konular\n- puts\n"),
            ("ruby-temeller", "Temeller: Array/Hash", "### Konular\n- array/hash\n"),
            ("ruby-fonksiyon", "Metotlar ve Block", "### Konular\n- block\n"),
            ("ruby-oop", "OOP ve Module", "### Konular\n- class/module\n"),
            ("ruby-gem", "Gem ve Ekosistem", "### Konular\n- gem\n"),
            ("ruby-test", "Test Yaklaşımı", "### Konular\n- rspec mantığı\n"),
        ],
        "go": [
            ("go-giris", "Giriş", "### Konular\n- package main\n"),
            ("go-temeller", "Temeller: Tipler ve Fonksiyonlar", "### Konular\n- func\n- slice/map\n"),
            ("go-struct", "Struct ve Interface", "### Konular\n- struct\n- interface\n"),
            ("go-error", "Error Handling", "### Konular\n- error\n"),
            ("go-concurrency", "Concurrency: Goroutine ve Channel", "### Konular\n- goroutine\n- channel\n"),
            ("go-test", "Testing", "### Konular\n- testing paketi\n"),
        ],
        "rust": [
            ("rust-giris", "Giriş", "### Konular\n- cargo\n"),
            ("rust-temeller", "Temeller: Ownership ve Borrowing", "### Konular\n- ownership\n"),
            ("rust-collections", "Collections ve Error Handling", "### Konular\n- Vec/HashMap\n- Result\n"),
            ("rust-traits", "Traits ve Generics", "### Konular\n- trait\n"),
            ("rust-lifetime", "Lifetimes (Giriş)", "### Konular\n- lifetime\n"),
            ("rust-async", "Async (Giriş)", "### Konular\n- async\n"),
            ("rust-test", "Test", "### Konular\n- unit test\n"),
        ],
        "r": [
            ("r-giris", "Giriş", "### Konular\n- R basics\n"),
            ("r-temeller", "Temeller: Vektör, Veri Çerçevesi", "### Konular\n- vector\n- data.frame\n"),
            ("r-plot", "Görselleştirme", "### Konular\n- plot\n"),
            ("r-istatistik", "Temel İstatistik", "### Konular\n- mean/median\n"),
            ("r-paket", "Paketler", "### Konular\n- install.packages\n"),
        ],
        "matlab": [
            ("matlab-giris", "Giriş", "### Konular\n- script\n"),
            ("matlab-matris", "Vektör ve Matris Temelleri", "### Konular\n- matrix\n"),
            ("matlab-fonksiyon", "Fonksiyonlar", "### Konular\n- function\n"),
            ("matlab-plot", "Plot ve Görselleştirme", "### Konular\n- plot\n"),
            ("matlab-toolbox", "Toolbox Mantığı", "### Konular\n- toolbox\n"),
        ],
        "sql": [
            ("sql-giris", "SQL’e Giriş", "### Konular\n- tablo\n- satır\n"),
            ("sql-temeller", "SQL Temelleri: SELECT, WHERE, ORDER", "### Konular\n- SELECT\n- WHERE\n"),
            ("sql-joins", "JOIN ve İlişkiler", "### Konular\n- join\n"),
            ("sql-group", "GROUP BY ve Aggregation", "### Konular\n- group by\n- count\n"),
            ("sql-index", "Index ve Performans", "### Konular\n- index\n"),
            ("sql-transactions", "Transaction", "### Konular\n- begin/commit\n"),
            ("sql-window", "Window Functions (Giriş)", "### Konular\n- row_number\n"),
        ],
    }

    added = 0
    for lang in catalog.get("languages", []):
        lid = (lang.get("id", "") or "").strip().lower()
        if lid not in curriculum:
            continue
        topics = lang.get("topics") or []
        lang["topics"] = topics
        existing = {t.get("id", "") for t in topics if isinstance(t, dict)}
        for tid, title, seed in curriculum[lid]:
            if tid in existing:
                continue
            topics.append(
                {
                    "id": tid,
                    "title": title,
                    "contentMarkdown": seed,
                    "questions": [],
                    "compilerChallenges": [],
                }
            )
            existing.add(tid)
            added += 1
    return added


def sort_topics_by_curriculum(catalog: dict) -> int:
    """
    Sort topics in each language from beginner -> advanced.
    Uses the curriculum order (ids). Unknown topics keep their relative order and go last.
    Returns number of languages sorted.
    """
    # Keep in sync with ensure_curriculum() keys
    curriculum_ids: dict[str, list[str]] = {
        lid: [tid for (tid, _title, _seed) in topics]
        for lid, topics in {
            **{
                # NOTE: we reuse the same structure by re-declaring minimal view
            }
        }.items()
    }
    # The dict above is empty placeholder; we'll build from ensure_curriculum's curriculum
    # by reconstructing it once here (to avoid duplicating the entire map again).
    # Easiest and safe: read the ids from the curriculum literal inside ensure_curriculum
    # is not possible directly, so we rebuild a compact id-only map here.
    curriculum_ids = {
        "c": ["c-giris", "c-degiskenler", "c-operatorler", "c-kontrol-akisi", "c-fonksiyonlar", "c-array-string", "c-pointer-bellek", "c-struct", "c-dosya", "c-debug-perf"],
        "python": ["py-kurulum", "py-degiskenler", "py-kosul-dongu", "py-fonksiyonlar", "py-koleksiyonlar", "py-string", "py-dosya", "py-hatalar", "py-oop", "py-ileri"],
        "javascript": ["js-giris", "js-tipler", "js-kontrol", "js-fonksiyon", "js-obj-array", "js-dom", "js-async", "js-moduller", "js-test", "js-proje"],
        "typescript": ["ts-giris", "ts-tip-sistemi", "ts-union", "ts-generics", "ts-moduller", "ts-uzmanliga-gecis"],
        "java": ["java-giris", "java-degiskenler", "java-kontrol-akisi", "java-oop", "java-collections", "java-streams", "java-exceptions", "java-concurrency", "java-test"],
        "dart": ["dart-giris", "dart-degiskenler", "dart-kontrol-akisi", "dart-fonksiyonlar", "dart-collections", "dart-async", "dart-oop", "dart-test"],
        "swift": ["swift-giris", "swift-temeller", "swift-kontrol-akisi", "swift-fonksiyon", "swift-struct-class", "swift-protokoller", "swift-async", "swift-test"],
        "kotlin": ["kotlin-giris", "kotlin-temeller", "kotlin-fonksiyon", "kotlin-collections", "kotlin-oop", "kotlin-coroutines", "kotlin-test"],
        "php": ["php-giris", "php-syntax", "php-fonksiyon", "php-oop", "php-web", "php-guvenlik", "php-composer"],
        "ruby": ["ruby-giris", "ruby-temeller", "ruby-fonksiyon", "ruby-oop", "ruby-gem", "ruby-test"],
        "go": ["go-giris", "go-temeller", "go-struct", "go-error", "go-concurrency", "go-test"],
        "rust": ["rust-giris", "rust-temeller", "rust-collections", "rust-traits", "rust-lifetime", "rust-async", "rust-test"],
        "r": ["r-giris", "r-temeller", "r-plot", "r-istatistik", "r-paket"],
        "matlab": ["matlab-giris", "matlab-matris", "matlab-fonksiyon", "matlab-plot", "matlab-toolbox"],
        "sql": ["sql-giris", "sql-temeller", "sql-joins", "sql-group", "sql-index", "sql-transactions", "sql-window"],
    }

    sorted_langs = 0
    for lang in catalog.get("languages", []):
        lid = (lang.get("id", "") or "").strip().lower()
        topics = lang.get("topics")
        if not isinstance(topics, list) or not topics:
            continue
        order = curriculum_ids.get(lid)
        if not order:
            continue
        rank = {tid: i for i, tid in enumerate(order)}
        indexed = list(enumerate(topics))

        def key(item):
            idx, t = item
            tid = (t.get("id", "") if isinstance(t, dict) else "")
            r = rank.get(tid)
            # Known topics first by curriculum order; unknown topics last but stable.
            return (0, r, 0) if r is not None else (1, 10_000_000, idx)

        indexed.sort(key=key)
        lang["topics"] = [t for _idx, t in indexed]
        sorted_langs += 1
    return sorted_langs


def make_generic_questions(
    lang_id: str,
    lang_name: str,
    topic_id: str,
    topic_title: str,
    md: str,
    need: int,
    existing_ids: set[str],
    global_seen_prompts: set[str],
):
    """Backward-compatible wrapper (kept for older calls)."""
    # NOTE: New implementation generates a fixed 20 questions per difficulty (60 total)
    # via build_quiz_bank(). The 'need' argument is ignored except for legacy callers.
    lid = (lang_id or "").strip().lower()
    ln = lang_name.strip()
    tid = (topic_id or "").strip().lower()
    tt = topic_title.strip()

    # Keyword extraction can be polluted if the lesson markdown is generic or mixed.
    # Filter obvious cross-topic SQL terms for non-SQL topics/languages.
    def _cat_from_tid(tid2: str) -> str:
        t2 = (tid2 or "").lower()
        if any(x in t2 for x in ("sql", "joins", "index", "window", "transactions", "group")):
            return "sql"
        if any(x in t2 for x in ("memory", "pointer", "lifetime", "bellek")):
            return "memory"
        if any(x in t2 for x in ("kosul", "kontrol", "dongu")):
            return "control"
        if any(x in t2 for x in ("fonksiyon", "function")):
            return "functions"
        if any(x in t2 for x in ("koleksiyon", "collections", "stl", "obj-array", "array-obj")):
            return "collections"
        if any(x in t2 for x in ("string", "array-string")):
            return "string"
        if any(x in t2 for x in ("dosya", "file")):
            return "files"
        if any(x in t2 for x in ("hata", "exception", "error")):
            return "errors"
        if any(x in t2 for x in ("oop", "struct", "class", "traits", "protokol", "protocol")):
            return "oop"
        if any(x in t2 for x in ("async", "concurrency", "coroutines")):
            return "async"
        if any(x in t2 for x in ("test",)):
            return "testing"
        if any(x in t2 for x in ("giris", "kurulum", "baslangic")):
            return "intro"
        if any(x in t2 for x in ("degisken", "değişken", "tip", "tür", "tur", "types", "type", "operator", "operat")):
            return "types"
        return "advanced"

    _cat = _cat_from_tid(tid)
    kws = extract_keywords(md or "", topic_title)
    if lid != "sql" and _cat != "sql":
        sql_terms = {
            "select", "from", "where", "join", "left", "right", "inner", "outer",
            "group", "by", "order", "limit", "insert", "update", "delete",
            "transaction", "commit", "rollback", "index", "explain",
        }
        kws = [k for k in kws if k.lower() not in sql_terms]
    # For intro/installation topics, prefer stable language/topic anchors over noisy markdown.
    if _cat == "intro":
        base_intro = [tt, "kurulum", "giriş", "syntax", "değişken", "çıktı", "print"]
        # Remove empties and keep order unique
        seen = set()
        kws2 = []
        for x in base_intro + kws:
            x = (x or "").strip()
            if not x or x.lower() in seen:
                continue
            seen.add(x.lower())
            kws2.append(x)
        kws = kws2[:10]
    kw1 = kws[0] if len(kws) > 0 else topic_title
    kw2 = kws[1] if len(kws) > 1 else "sözdizimi"
    kw3 = kws[2] if len(kws) > 2 else "örnek"
    # Global de-dupe is intentionally DISABLED for the new fixed-size banks,
    # because it can prevent reaching required counts. We only de-dupe within a topic.
    # (Kept for compatibility with the old wrapper signature.)
    _ = global_seen_prompts

    def build_quiz_bank(target_per_diff: int = 20) -> list[dict]:
        """
        Build exactly target_per_diff questions for each difficulty (easy/medium/hard)
        using topic-id + lesson keywords + optional code blocks.
        """
        # Local mapping: keep quiz generator independent of topic_bank() internals.
        # We can't reference the inner helper from topic_bank() here; use a small local mapping
        # based on the topic id itself as a safe fallback.
        # (Exact mapping is already covered via topic-id-specific blocks and keywords.)
        if any(x in tid for x in ("kosul", "kontrol", "dongu")):
            cat = "control"
        elif any(x in tid for x in ("fonksiyon", "function")):
            cat = "functions"
        elif any(x in tid for x in ("koleksiyon", "collections", "stl", "obj-array", "array-obj")):
            cat = "collections"
        elif any(x in tid for x in ("string", "array-string")):
            cat = "string"
        elif any(x in tid for x in ("dosya", "file")):
            cat = "files"
        elif any(x in tid for x in ("hata", "exception", "error")):
            cat = "errors"
        elif any(x in tid for x in ("oop", "struct", "class", "traits", "protokol", "protocol")):
            cat = "oop"
        elif any(x in tid for x in ("async", "concurrency", "coroutines")):
            cat = "async"
        elif any(x in tid for x in ("test",)):
            cat = "testing"
        elif any(x in tid for x in ("sql", "joins", "index", "window", "transactions", "group")):
            cat = "sql"
        elif any(x in tid for x in ("memory", "pointer", "lifetime", "bellek")):
            cat = "memory"
        elif any(x in tid for x in ("giris", "kurulum", "baslangic")):
            cat = "intro"
        else:
            cat = "advanced"

        def mk_id(diff: str, idx: int) -> str:
            return next_id(existing_ids, f"auto-{slugify(ln)}-{slugify(tt)}-{diff}-q")

        def add(out: list[dict], diff: str, typ: str, prompt: str, payload, ans, exp: str):
            # Prevent within-topic repetition (especially important with fixed-size banks).
            if not hasattr(add, "_seen"):
                add._seen = set()  # type: ignore[attr-defined]
            key = diff + "|" + norm_prompt(prompt)
            if key in add._seen:  # type: ignore[attr-defined]
                return
            add._seen.add(key)  # type: ignore[attr-defined]
            qid = mk_id(diff, len(out) + 1)
            if typ == "tf":
                out.append(
                    {
                        "id": qid,
                        "type": "tf",
                        "difficulty": diff,
                        "prompt": prompt,
                        "answerBool": bool(ans),
                        "explanation": exp,
                    }
                )
            elif typ == "mcq":
                choices = [str(x) for x in (payload or [])]
                # Deduplicate choices while keeping order
                seen_c = set()
                uniq = []
                for c in choices:
                    if c in seen_c:
                        continue
                    seen_c.add(c)
                    uniq.append(c)
                if len(uniq) < 2:
                    return
                aidx = int(ans)
                if aidx < 0 or aidx >= len(uniq):
                    aidx = 0
                out.append(
                    {
                        "id": qid,
                        "type": "mcq",
                        "difficulty": diff,
                        "prompt": prompt,
                        "choices": uniq,
                        "answerIndex": aidx,
                        "explanation": exp,
                    }
                )
            else:
                out.append(
                    {
                        "id": qid,
                        "type": "fill",
                        "difficulty": diff,
                        "prompt": prompt,
                        "answerText": str(payload or ""),
                        "explanation": exp,
                    }
                )

        # Use code blocks first: they are the most topic-specific.
        @dataclass(frozen=True)
        class _CodeBlock:
            lang: str
            code: str

        def _extract_code_blocks(markdown: str) -> list[_CodeBlock]:
            md2 = markdown or ""
            blocks2: list[_CodeBlock] = []
            for m in re.finditer(r"```([a-zA-Z0-9_+-]*)\n([\s\S]*?)\n```", md2):
                lang = (m.group(1) or "").strip().lower()
                code = (m.group(2) or "").rstrip()
                if not code.strip():
                    continue
                blocks2.append(_CodeBlock(lang=lang, code=code))
            return blocks2

        def _unescape_newlines(s: str) -> str:
            return s.replace("\\n", "\n").replace("\\t", "\t")

        def _infer_output_literal(language_id: str, code: str) -> str | None:
            s = (code or "").strip()
            lid2 = (language_id or "").lower()
            if lid2 == "python":
                m = re.search(r"""^print\(\s*(['"])(.*?)\1\s*\)\s*$""", s, re.MULTILINE)
                if m:
                    return _unescape_newlines(m.group(2)) + "\n"
            if lid2 in ("javascript", "typescript"):
                m = re.search(r"""^console\.log\(\s*(['"])(.*?)\1\s*\)\s*;?\s*$""", s, re.MULTILINE)
                if m:
                    return _unescape_newlines(m.group(2)) + "\n"
            if lid2 == "dart":
                m = re.search(r"""^print\(\s*(['"])(.*?)\1\s*\)\s*;?\s*$""", s, re.MULTILINE)
                if m:
                    return _unescape_newlines(m.group(2)) + "\n"
            if lid2 in ("c", "cpp"):
                m = re.search(r"""printf\(\s*(['"])(.*?)\1\s*\)\s*;""", s)
                if m:
                    return _unescape_newlines(m.group(2))
            if lid2 in ("java", "kotlin"):
                m = re.search(r"""System\.out\.println\(\s*(['"])(.*?)\1\s*\)\s*;""", s)
                if m:
                    return _unescape_newlines(m.group(2)) + "\n"
            if lid2 == "sql":
                m = re.search(r"""^\s*SELECT\s+([0-9]+)\s*;\s*$""", s, re.IGNORECASE | re.MULTILINE)
                if m:
                    return f"{m.group(1)}\n"
            return None

        def _make_missing_token_question(language_id: str, code: str) -> tuple | None:
            lid2 = (language_id or "").lower()
            if lid2 == "python":
                lines = code.splitlines()
                for i, line in enumerate(lines):
                    if re.match(r"^\s*(def|if|for|while)\b.*:\s*$", line):
                        new_line = re.sub(r":\s*$", "____", line)
                        shown = "\n".join(lines[:i] + [new_line] + lines[i + 1 :])
                        return ("fill", "medium", f"[{ln} • {tt}] Aşağıdaki kodda eksik olan sembolü doldur.\n\n{shown}", ":", None, "Python'da satır ':' ile biter.")
                return None
            if lid2 in ("javascript", "typescript", "dart", "java", "kotlin", "swift", "php", "c", "cpp", "go", "rust"):
                lines = code.splitlines()
                for i, line in enumerate(lines):
                    l = line.rstrip()
                    if not l or l.strip().startswith(("//", "#", "--")):
                        continue
                    if re.search(r"\b(print|printf|console\.log|System\.out\.println)\b", l) and l.endswith(";"):
                        new_line = l[:-1] + "____"
                        shown = "\n".join(lines[:i] + [new_line] + lines[i + 1 :])
                        return ("fill", "medium", f"[{ln} • {tt}] Aşağıdaki kodda eksik olan sembolü doldur.\n\n{shown}", ";", None, "Bu dil ailesinde çoğu ifade ';' ile biter.")
                return None
            return None

        blocks = _extract_code_blocks(md or "")

        def add_from_code(out_easy: list[dict], out_med: list[dict], out_hard: list[dict]):
            used = 0
            for cb in blocks:
                if used >= 18:  # keep space for templates
                    break
                out_lit = _infer_output_literal(lid, cb.code)
                if out_lit is not None and len(out_easy) < target_per_diff:
                    add(
                        out_easy,
                        "easy",
                        "mcq",
                        f"[{ln} • {tt}] Bu kodun çıktısı nedir?\n\n{cb.code}",
                        [out_lit.rstrip("\n"), "(çıktı üretmez)", "Hata verir", "Bilinemez"],
                        0,
                        "Bu soru doğrudan dersteki koddan üretilmiştir.",
                    )
                    used += 1
                mt = _make_missing_token_question(lid, cb.code)
                if mt is not None and len(out_med) < target_per_diff:
                    typ, diff, prompt, payload, ans, exp = mt
                    add(out_med, "medium", typ, prompt, payload, ans, exp)
                    used += 1
                if len(out_hard) < target_per_diff:
                    # concept identification from the code block
                    c = cb.code
                    construct = None
                    if re.search(r"\bfor\b", c) or re.search(r"\bwhile\b", c):
                        construct = ("Döngü", 0)
                    elif re.search(r"\bif\b", c) or re.search(r"\bswitch\b", c):
                        construct = ("Koşul", 1)
                    elif re.search(r"\bdef\b", c) or re.search(r"\bfunction\b", c) or re.search(r"\bfn\b", c) or re.search(r"\bfunc\b", c) or re.search(r"\bfun\b", c):
                        construct = ("Fonksiyon", 2)
                    elif re.search(r"\bclass\b", c) or re.search(r"\bstruct\b", c) or re.search(r"\binterface\b", c) or re.search(r"\bprotocol\b", c) or re.search(r"\btrait\b", c):
                        construct = ("OOP", 3)
                    if construct is not None:
                        add(
                            out_hard,
                            "hard",
                            "mcq",
                            f"[{ln} • {tt}] Bu kod parçası ağırlıklı olarak hangi kavramı gösteriyor?\n\n{cb.code}",
                            ["Döngü", "Koşul", "Fonksiyon", "OOP"],
                            construct[1],
                            "Bu soru doğrudan dersteki koddan üretilmiştir.",
                        )
                        used += 1

        # Topic-specific templates: generate 20 unique per difficulty.
        def fill_templates(out_easy: list[dict], out_med: list[dict], out_hard: list[dict]):
            a2 = LANG_ANCHORS.get(lid) or LANG_ANCHORS.get("javascript")
            null_word = a2.get("null", "null")
            func_word = a2.get("func", "function")
            comment = a2.get("comment", "//")

            def cyc(i: int, items: list):
                return items[(i - 1) % len(items)]

            # EASY: mostly recognition + simple outputs + concrete facts
            for i in range(1, 9999):
                if len(out_easy) >= target_per_diff:
                    break
                k = (i - 1) % 6
                if cat == "intro":
                    if k == 0:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Yorum satırı hangisiyle başlar?", [comment, "#", "--", "/* */"], 0, "Dil sözdizimi sorusu.")
                    elif k == 1:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Boş değer hangisidir?", [null_word, "0", "''", "undefined"], 0, "Dil semantiği sorusu.")
                    elif k == 2:
                        add(out_easy, "easy", "fill", f"[{ln} • {tt}] Fonksiyon anahtar kelimesi/kalıbı: ______", func_word, None, "Bu dilde fonksiyon tanımı bu anahtar kelimeyle yapılır.")
                    elif k == 3:
                        add(out_easy, "easy", "tf", f"[{ln} • {tt}] Derleyici/yorumlayıcı hata mesajları sorunun yerini gösterir.", None, True, "Hata mesajı okuma.")
                    elif k == 4:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Aşağıdakilerden hangisi dersteki anahtar kelimelerden biridir?", [kw1, "UI", "donanım", "renk"], 0, "İçerik anahtar kelime sorusu.")
                    else:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Bu konuda en çok ne öğrenilir?", [kw1, kw2, "tasarım", "donanım"], 0, "Konu anahtar kelime sorusu.")
                elif cat == "types":
                    v = 10 + ((i * 7) % 90)
                    if k == 0:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Boolean değerler genelde hangisidir?", [f"{a2['bool_true']}/{a2['bool_false']}", "yes/no", "T/F", "1/2"], 0, "Boolean temeli.")
                    elif k == 1:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Null/boş değer kontrolü neden önemlidir?", ["Null reference hatasını önler", "UI çizer", "Index oluşturur", "Derlemeyi kapatır"], 0, "Null güvenliği.")
                    elif k == 2:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] '{v}' gibi bir değer genelde hangi tiptedir?", ["int/number", "string", "bool", "function"], 0, "Basit tip tanıma.")
                    elif k == 3:
                        add(out_easy, "easy", "tf", f"[{ln} • {tt}] Tip dönüşümünde veri kaybı olabilir.", None, True, "Casting riski.")
                    elif k == 4:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Tip dönüşümü (casting) en çok hangi riski taşır?", ["Veri kaybı", "Renk", "Font", "Yorum"], 0, "Casting riski.")
                    else:
                        add(out_easy, "easy", "fill", f"[{ln} • {tt}] Boş değer sembolü/kelimesi: ______", null_word, None, "Dil boş değer temsilcisi.")
                elif cat == "control":
                    n = 5 + (i % 20)
                    if k == 0:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Koşulların amacı nedir?", ["Karar vermek", "Dosya okumak", "Bellek silmek", "UI çizmek"], 0, "Kontrol akışı.")
                    elif k == 1:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Döngülerin amacı nedir?", ["Tekrarlı işleri yapmak", "Sadece yazdırmak", "Index yaratmak", "Import yapmak"], 0, "Döngü temeli.")
                    elif k == 2:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Off-by-one hatası en çok neyle ilgilidir?", ["Döngü sınırları", "Yorum", "Dosya", "Renk"], 0, "Sınır hatası.")
                    elif k == 3:
                        add(out_easy, "easy", "tf", f"[{ln} • {tt}] break/continue döngü akışını değiştirebilir.", None, True, "Akış kontrolü.")
                    elif k == 4:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] 1..{n} arası kaç sayı 2'ye bölünür?", [str(n//2), str((n+1)//2), str(n), "0"], 0, "Basit akış mantığı.")
                    else:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] En doğru ifade hangisi?", ["Koşul boolean üretir/kullanır", "Koşul sadece yazdırır", "Koşul UI içindir", "Koşul dosya içindir"], 0, "Koşul mantığı.")
                elif cat == "functions":
                    a = (i % 9) + 2
                    b = (i % 7) + 3
                    if k == 0:
                        add(out_easy, "easy", "fill", f"[{ln} • {tt}] Fonksiyon anahtar kelimesi: ______", func_word, None, "Dil fonksiyon anahtar kelimesi.")
                    elif k == 1:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Fonksiyonun amacı nedir?", ["Kodu tekrar etmemek", "UI çizmek", "Index yapmak", "Bellek silmek"], 0, "Fonksiyon temeli.")
                    elif k == 2:
                        add(out_easy, "easy", "tf", f"[{ln} • {tt}] Parametreler fonksiyona veri taşır.", None, True, "Parametre temeli.")
                    elif k == 3:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] add({a},{b}) fonksiyonu doğruysa sonuç ne olur?", [str(a+b), str(a*b), str(a-b), str(b-a)], 0, "Basit fonksiyon mantığı.")
                    elif k == 4:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Return ne yapar?", ["Sonuç döndürür", "Yorum ekler", "Dosya açar", "Thread açar"], 0, "Return temeli.")
                    else:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Aşağıdakilerden hangisi fonksiyon için iyi pratiktir?", ["Tek sorumluluk", "Her şeyi global", "Her şeyi tek yerde", "İsimsiz değişkenler"], 0, "Fonksiyon pratik.")
                elif cat == "collections":
                    if k == 0:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Benzersiz eleman için hangisi?", ["Set", "List/Array", "String", "Number"], 0, "Set unique.")
                    elif k == 1:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Anahtar→değer için hangisi?", ["Map/Dict", "List/Array", "Queue", "Stack"], 0, "Map/Dict.")
                    elif k == 2:
                        add(out_easy, "easy", "tf", f"[{ln} • {tt}] Liste/array sıralı eleman tutar.", None, True, "Sıralı veri.")
                    elif k == 3:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Filtreleme ne yapar?", ["Şarta uyanları seçer", "Ters çevirir", "Sil", "Kopyala"], 0, "Filter.")
                    elif k == 4:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Uzunluğu 3 olan bir dizide son index hangisidir?", ["2", "3", "1", "0"], 0, "Index temeli.")
                    else:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Bu konuda geçen anahtar kelime hangisi olabilir?", [kw1, "render", "shader", "bios"], 0, "Konu keyword.")
                elif cat == "string":
                    s = cyc(i, [kw1, kw2, kw3, tt]).replace("'", "")
                    if k == 0:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] '{s}' uzunluğu neyi ifade eder?", ["Karakter sayısı", "Dosya boyutu", "RAM", "UI"], 0, "String length.")
                    elif k == 1:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Trim ne yapar?", ["Boşlukları kaldırır", "Toplar", "Sıralar", "Pointer üretir"], 0, "Trim.")
                    elif k == 2:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Substring/slice ne işe yarar?", ["Parça almak", "Dosya açmak", "Thread", "Index"], 0, "Substring.")
                    elif k == 3:
                        add(out_easy, "easy", "tf", f"[{ln} • {tt}] String birleştirme çoğu dilde vardır.", None, True, "Concat.")
                    elif k == 4:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Büyük/küçük harf dönüşümü hangisine örnektir?", ["String işlemi", "Bellek yönetimi", "SQL join", "Thread"], 0, "String ops.")
                    else:
                        add(out_easy, "easy", "fill", f"[{ln} • {tt}] Boşluk temizleme işleminin adı: ______", "trim", None, "Trim kavramı.")
                elif cat == "files":
                    if k == 0:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Dosya işlemlerinde en kritik adım?", ["Kapatmak", "UI", "Index", "Thread"], 0, "Close.")
                    elif k == 1:
                        add(out_easy, "easy", "tf", f"[{ln} • {tt}] Hatalı path dosya okuma hatası üretir.", None, True, "File not found.")
                    elif k == 2:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Encoding neden önemli?", ["Karakterler bozulmasın", "Renk", "Font", "UI"], 0, "UTF-8.")
                    elif k == 3:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Append modu ne yapar?", ["Sona ekler", "Siler", "Sadece okur", "RAM"], 0, "Append.")
                    elif k == 4:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Dosya okuma sonrası en doğru adım?", ["Kapatmak", "Silmek", "Formatlamak", "Rename"], 0, "Close.")
                    else:
                        add(out_easy, "easy", "fill", f"[{ln} • {tt}] Dosyayı kapatma işlemi önemlidir çünkü ______ yönetimi yapılır.", "kaynak", None, "Resource management.")
                elif cat == "errors":
                    if k == 0:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Exception yönetiminin amacı?", ["Kontrollü ele almak", "UI", "Index", "Thread"], 0, "Error handling.")
                    elif k == 1:
                        add(out_easy, "easy", "tf", f"[{ln} • {tt}] İlk hata genelde en kritiktir.", None, True, "First error.")
                    elif k == 2:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Stack trace ne verir?", ["Çağrı zinciri", "UI", "Index", "Font"], 0, "Stack trace.")
                    elif k == 3:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] En iyi yaklaşım?", ["Spesifik yakala", "Hepsini yut", "Hiç yakalama", "Sadece print"], 0, "Specific catch.")
                    elif k == 4:
                        add(out_easy, "easy", "fill", f"[{ln} • {tt}] Hata mesajını okumak ______ bulmayı hızlandırır.", "sorunu", None, "Debugging.")
                    else:
                        add(out_easy, "easy", "tf", f"[{ln} • {tt}] Hata yönetimi kullanıcı deneyimini iyileştirebilir.", None, True, "UX.")
                elif cat == "oop":
                    if k == 0:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Encapsulation nedir?", ["Kontrollü erişim", "Global", "Public", "UI"], 0, "Encapsulation.")
                    elif k == 1:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Polymorphism nedir?", ["Aynı arayüz farklı davranış", "Dosya", "SQL", "Thread"], 0, "Polymorphism.")
                    elif k == 2:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Constructor ne yapar?", ["Başlatır", "Siler", "Index", "Render"], 0, "Constructor.")
                    elif k == 3:
                        add(out_easy, "easy", "tf", f"[{ln} • {tt}] Interface/trait/protocol sözleşme sağlar.", None, True, "Contract.")
                    elif k == 4:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] OOP'in amacı hangisine en yakındır?", ["Modelleme", "UI boyama", "BIOS", "Shader"], 0, "Modeling.")
                    else:
                        add(out_easy, "easy", "tf", f"[{ln} • {tt}] Composition bazen inheritance'tan daha esnektir.", None, True, "Design.")
                elif cat == "async":
                    if k == 0:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Async'in amacı?", ["Bloklamadan beklemeyi yönetmek", "UI", "Index", "Font"], 0, "Async.")
                    elif k == 1:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Race condition nedir?", ["Eşzamanlı erişim hatası", "Syntax", "UI", "Index"], 0, "Race.")
                    elif k == 2:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Deadlock nedir?", ["Kilitlenme", "Hız", "Tip", "Dosya"], 0, "Deadlock.")
                    elif k == 3:
                        add(out_easy, "easy", "tf", f"[{ln} • {tt}] Bağımsız işler paralel yürüyebilir.", None, True, "Parallelism.")
                    elif k == 4:
                        add(out_easy, "easy", "fill", f"[{ln} • {tt}] Async dünyada bekleme birimi (Promise/Future) gibi bir yapıdır: ______", "promise/future", None, "Concept.")
                    else:
                        add(out_easy, "easy", "tf", f"[{ln} • {tt}] Async kodda hata yönetimi önemlidir.", None, True, "Errors.")
                elif cat == "testing":
                    if k == 0:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Unit test neyi hedefler?", ["İzole davranış", "Tüm sistem", "UI", "DB"], 0, "Unit test.")
                    elif k == 1:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Integration test neyi hedefler?", ["Bileşenlerin beraber çalışması", "Değişken adı", "Yorum", "Index"], 0, "Integration.")
                    elif k == 2:
                        add(out_easy, "easy", "tf", f"[{ln} • {tt}] Testler regresyonu yakalar.", None, True, "Regression.")
                    elif k == 3:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Mock/stub neden kullanılır?", ["Bağımlılığı izole etmek", "UI", "Font", "Index"], 0, "Isolation.")
                    elif k == 4:
                        add(out_easy, "easy", "fill", f"[{ln} • {tt}] Tek bir fonksiyonu izole test etmek: ______ test", "unit", None, "Unit test.")
                    else:
                        add(out_easy, "easy", "tf", f"[{ln} • {tt}] Testler güvenli refactor yapmayı kolaylaştırır.", None, True, "Safety.")
                elif cat == "sql":
                    if k == 0:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Filtreleme için?", ["WHERE", "GROUP BY", "ORDER BY", "LIMIT"], 0, "WHERE.")
                    elif k == 1:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] JOIN ne için?", ["Tabloları birleştirmek", "UI", "Thread", "Dosya"], 0, "JOIN.")
                    elif k == 2:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] GROUP BY ne yapar?", ["Gruplar", "Sıralar", "Limit", "Sil"], 0, "Group.")
                    elif k == 3:
                        add(out_easy, "easy", "tf", f"[{ln} • {tt}] NULL için = yerine IS NULL gerekir.", None, True, "NULL compare.")
                    elif k == 4:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Index genelde neyi hızlandırır?", ["Okuma sorguları", "UI", "Font", "Compile"], 0, "Index.")
                    else:
                        add(out_easy, "easy", "fill", f"[{ln} • {tt}] Sorgu planını görmek için tipik komut: ______", "EXPLAIN", None, "Explain.")
                elif cat == "memory":
                    if k == 0:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Pointer nedir?", ["Bellek adresi", "Metin", "Sayı", "UI"], 0, "Pointer.")
                    elif k == 1:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Memory leak nedir?", ["Belleği serbest bırakmamak", "UI", "SQL", "Font"], 0, "Leak.")
                    elif k == 2:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Dangling pointer nedir?", ["Geçersiz adres", "Renk", "Index", "Thread"], 0, "Dangling.")
                    elif k == 3:
                        add(out_easy, "easy", "tf", f"[{ln} • {tt}] Bellek hataları çökme üretebilir.", None, True, "Crash.")
                    elif k == 4:
                        add(out_easy, "easy", "fill", f"[{ln} • {tt}] Adres operatörü örneği: ______x (dile göre)", "&", None, "Address operator.")
                    else:
                        add(out_easy, "easy", "tf", f"[{ln} • {tt}] Pointer kullanımı dikkat gerektirir.", None, True, "Safety.")
                else:  # advanced
                    # Advanced topics should still be tied to topic keywords, not generic advice.
                    if k == 0:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Bu konu hangi kavramla daha çok ilişkilidir?", [kw1, kw2, "UI", "donanım"], 0, "Keyword.")
                    elif k == 1:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] '{kw2}' en çok hangi alanda geçer?", ["bu konu", "UI", "donanım", "tasarım"], 0, "Keyword.")
                    elif k == 2:
                        add(out_easy, "easy", "tf", f"[{ln} • {tt}] Bu konu genelde birden fazla kavramı birleştirir.", None, True, "Advanced.")
                    elif k == 3:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Aşağıdakilerden hangisi bu konunun anahtar kelimesidir?", [kw1, "shader", "bios", "font"], 0, "Keyword.")
                    elif k == 4:
                        add(out_easy, "easy", "fill", f"[{ln} • {tt}] Bu konudan bir anahtar kelime yaz: ______", kw1, None, "Keyword.")
                    else:
                        add(out_easy, "easy", "mcq", f"[{ln} • {tt}] Bu konu için en ilgili terim hangisi?", [kw2, kw1, "UI", "donanım"], 0, "Keyword.")

            # MEDIUM: code reading + edge cases + small reasoning
            for i in range(1, 9999):
                if len(out_med) >= target_per_diff:
                    break
                k = (i - 1) % 8
                if cat == "control":
                    n = 10 + (i % 25)
                    if k == 0:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] 1..{n} arası 3'e bölünen kaç sayı var?", [str(n//3), str((n+2)//3), str((n+3)//3), "0"], 1, "Bölünebilirlik sayımı.")
                    elif k == 1:
                        add(out_med, "medium", "tf", f"[{ln} • {tt}] Döngü koşulu hiç değişmiyorsa sonsuz döngü olur.", None, True, "Sonsuz döngü nedeni.")
                    elif k == 2:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Switch/çoklu seçim ne zaman uygundur?", ["Sabit çok seçenek", "Dosya okuma", "Pointer", "UI"], 0, "Seçim mantığı.")
                    elif k == 3:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Off-by-one hatasını azaltmak için en iyi yöntem?", ["Sınır değerleri test etmek", "Rastgele denemek", "Yorum silmek", "UI değiştirmek"], 0, "Edge-case testi.")
                    elif k == 4:
                        add(out_med, "medium", "fill", f"[{ln} • {tt}] Döngüden erken çıkmak için anahtar kelime: ______", "break", None, "Akış kontrolü.")
                    elif k == 5:
                        add(out_med, "medium", "fill", f"[{ln} • {tt}] Bir sonraki iterasyona geçmek için: ______", "continue", None, "Akış kontrolü.")
                    elif k == 6:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] 0..9 döngüsünde toplam iterasyon sayısı?", ["9", "10", "11", "0"], 1, "Sınır mantığı.")
                    else:
                        add(out_med, "medium", "tf", f"[{ln} • {tt}] Koşul ifadeleri boolean üretir/kullanır.", None, True, "Koşul mantığı.")
                elif cat == "functions":
                    a = 2 + (i % 9)
                    b = 3 + (i % 7)
                    if k == 0:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] f(x)=2x ise f({a}) nedir?", [str(2*a), str(a*a), str(a+2), str(a-2)], 0, "Fonksiyon okuma.")
                    elif k == 1:
                        add(out_med, "medium", "tf", f"[{ln} • {tt}] Pure function dış dünyayı değiştirmez.", None, True, "Pure function.")
                    elif k == 2:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Aşağıdakilerden hangisi daha iyi pratik?", ["Tek sorumluluk", "Global state", "Kopya kod", "İsimsiz değişken"], 0, "Design.")
                    elif k == 3:
                        add(out_med, "medium", "fill", f"[{ln} • {tt}] Parametre yerine sabit kullanmak yerine fonksiyon ______ almalıdır.", "parametre", None, "Parametre kullanımı.")
                    elif k == 4:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] add({a},{b}) sonucu?", [str(a+b), str(a*b), str(a-b), str(b-a)], 0, "Toplama.")
                    elif k == 5:
                        add(out_med, "medium", "tf", f"[{ln} • {tt}] Fonksiyon imzası (parametre/dönüş) API kontratıdır.", None, True, "API contract.")
                    elif k == 6:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Side effect örneği hangisidir?", ["Global değişkeni değiştirmek", "Sadece return", "Saf hesap", "Parametre kullanmak"], 0, "Side effect.")
                    else:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Default parametreler ne sağlar?", ["Opsiyonel çağrı", "UI", "Index", "Bellek"], 0, "Optional args.")
                elif cat == "collections":
                    if k == 0:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Map/Dict'te anahtar yoksa en güvenli yaklaşım?", ["Default/get kullanmak", "Direkt erişim", "UI", "Index"], 0, "Safe access.")
                    elif k == 1:
                        add(out_med, "medium", "tf", f"[{ln} • {tt}] Hash map ortalama O(1) erişim sağlayabilir.", None, True, "Complexity.")
                    elif k == 2:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Set ne zaman seçilir?", ["Tekrarsız eleman", "Sıralı liste", "Metin", "UI"], 0, "Set usage.")
                    elif k == 3:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Reduce/fold ne yapar?", ["Listeyi tek değere indirger", "Sıralar", "Ters çevirir", "Sil"], 0, "Reduce.")
                    elif k == 4:
                        add(out_med, "medium", "tf", f"[{ln} • {tt}] Büyük listede gereksiz kopyalar performansı düşürür.", None, True, "Perf.")
                    elif k == 5:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Bir listenin ortasından silme genelde neden pahalı?", ["Kaydırma gerekir", "UI", "SQL", "Thread"], 0, "Shift.")
                    elif k == 6:
                        add(out_med, "medium", "fill", f"[{ln} • {tt}] Benzersiz eleman yapısı: ______", "set", None, "Set.")
                    else:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] 'index out of range' hatası neyi gösterir?", ["Sınır aşımı", "UI", "SQL", "Font"], 0, "Bounds.")
                elif cat == "string":
                    s = cyc(i, [kw1, kw2, kw3, tt]).replace("'", "")
                    if k == 0:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] '{s}' için upper/lower işlemi hangi sınıftadır?", ["String işlemi", "Bellek", "SQL", "Thread"], 0, "String op.")
                    elif k == 1:
                        add(out_med, "medium", "tf", f"[{ln} • {tt}] Unicode nedeniyle bazı karakterlerin uzunluğu beklenenden farklı olabilir.", None, True, "Unicode.")
                    elif k == 2:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Substring sınırı yanlış olursa ne olur?", ["Hata veya yanlış sonuç", "UI", "Index", "Thread"], 0, "Bounds.")
                    elif k == 3:
                        add(out_med, "medium", "fill", f"[{ln} • {tt}] 'Boşlukları kaldırma' işlemine genelde ______ denir.", "trim", None, "Trim.")
                    elif k == 4:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] String birleştirme neden pahalı olabilir?", ["Yeni kopyalar oluşturur", "UI", "SQL", "Thread"], 0, "Copies.")
                    elif k == 5:
                        add(out_med, "medium", "tf", f"[{ln} • {tt}] String karşılaştırmasında büyük/küçük harf farkı önemlidir (case-sensitive).", None, True, "Case.")
                    elif k == 6:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Regex ne için kullanılır?", ["Pattern eşleştirme", "Bellek yönetimi", "SQL join", "Thread"], 0, "Regex.")
                    else:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Formatlama (interpolation) ne sağlar?", ["Okunabilir çıktı", "Pointer", "Index", "GC"], 0, "Format.")
                elif cat == "files":
                    if k == 0:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Dosya handle kapatılmazsa ne risk olur?", ["Kaynak sızıntısı", "UI", "SQL", "Font"], 0, "Resource leak.")
                    elif k == 1:
                        add(out_med, "medium", "tf", f"[{ln} • {tt}] try/finally veya with/use pattern dosyayı kapatmaya yardım eder.", None, True, "Cleanup.")
                    elif k == 2:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Text dosyası okurken en yaygın encoding?", ["UTF-8", "PNG", "MP3", "RAW"], 0, "UTF-8.")
                    elif k == 3:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Append vs overwrite farkı?", ["Append sona ekler", "Overwrite sona ekler", "Aynı", "UI"], 0, "Modes.")
                    elif k == 4:
                        add(out_med, "medium", "fill", f"[{ln} • {tt}] Dosya okuma hata türü örneği: ______ (file not found)", "not found", None, "Common error.")
                    elif k == 5:
                        add(out_med, "medium", "tf", f"[{ln} • {tt}] Büyük dosyada satır satır okumak bellek açısından daha iyidir.", None, True, "Streaming.")
                    elif k == 6:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] JSON dosyası okuduktan sonra tipik adım?", ["Parse etmek", "UI", "Index", "Thread"], 0, "Parse.")
                    else:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Dosyaya yazarken en kritik şey?", ["Doğru mod/encoding", "Renk", "Font", "UI"], 0, "Correctness.")
                elif cat == "errors":
                    if k == 0:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Spesifik exception yakalamak neden iyi?", ["Yanlış hataları yutmaz", "UI", "Index", "Thread"], 0, "Specific.")
                    elif k == 1:
                        add(out_med, "medium", "tf", f"[{ln} • {tt}] 'Bare except/catch' debug'ı zorlaştırabilir.", None, True, "Too broad.")
                    elif k == 2:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Stack trace hangi bilgiyi taşır?", ["Call stack", "UI", "Font", "Index"], 0, "Stack trace.")
                    elif k == 3:
                        add(out_med, "medium", "fill", f"[{ln} • {tt}] Hata zincirinde genelde önce ______ hata düzeltilir.", "ilk", None, "First error.")
                    elif k == 4:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Runtime error ile syntax error farkı?", ["Syntax parse edilemez", "Aynı", "UI", "Index"], 0, "Types.")
                    elif k == 5:
                        add(out_med, "medium", "tf", f"[{ln} • {tt}] Hata mesajı satır numarası çok değerlidir.", None, True, "Line.")
                    elif k == 6:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Exception propagation nedir?", ["Hatanın yukarı taşınması", "UI", "SQL", "Font"], 0, "Propagation.")
                    else:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Loglamak ne işe yarar?", ["Teşhis", "UI", "Index", "Thread"], 0, "Logs.")
                elif cat == "oop":
                    if k == 0:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Encapsulation hangi problemi azaltır?", ["Yanlış kullanım", "UI", "SQL", "Font"], 0, "API safety.")
                    elif k == 1:
                        add(out_med, "medium", "tf", f"[{ln} • {tt}] Polymorphism aynı çağrıyla farklı davranış demektir.", None, True, "Poly.")
                    elif k == 2:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Interface/trait/protocol ne sağlar?", ["Sözleşme", "Dosya", "Thread", "Index"], 0, "Contract.")
                    elif k == 3:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Composition ne sağlar?", ["Esneklik", "UI", "SQL", "Font"], 0, "Design.")
                    elif k == 4:
                        add(out_med, "medium", "tf", f"[{ln} • {tt}] Single Responsibility, class'ı sade tutar.", None, True, "SRP.")
                    elif k == 5:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Override ne işe yarar?", ["Metodu özelleştirir", "UI", "SQL", "Font"], 0, "Override.")
                    elif k == 6:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Abstract class ne sağlar?", ["Ortak temel + zorunlu metotlar", "UI", "Index", "Thread"], 0, "Abstract.")
                    else:
                        add(out_med, "medium", "fill", f"[{ln} • {tt}] Bir sınıfın verisini koruma yaklaşımı: ______", "encapsulation", None, "Encapsulation.")
                elif cat == "async":
                    if k == 0:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Await unutulursa ne olur?", ["Beklenen değer yerine future/promise", "UI", "SQL", "Font"], 0, "Await.")
                    elif k == 1:
                        add(out_med, "medium", "tf", f"[{ln} • {tt}] Paralel ve sıralı çalışma aynı değildir.", None, True, "Parallel vs sequential.")
                    elif k == 2:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Race condition çözümü için hangisi uygundur?", ["Lock/atomic", "UI", "Font", "Index"], 0, "Sync.")
                    elif k == 3:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Timeout ne işe yarar?", ["Sonsuz beklemeyi engeller", "UI", "Index", "Font"], 0, "Timeout.")
                    elif k == 4:
                        add(out_med, "medium", "tf", f"[{ln} • {tt}] Deadlock bir tür kilitlenmedir.", None, True, "Deadlock.")
                    elif k == 5:
                        add(out_med, "medium", "fill", f"[{ln} • {tt}] Asenkron iş birimi: ______ (promise/future gibi)", "future", None, "Async unit.")
                    elif k == 6:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Callback hell neyi ifade eder?", ["İç içe callback karmaşası", "UI", "SQL", "Font"], 0, "JS concept.")
                    else:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Structured concurrency neyi hedefler?", ["Yaşam döngüsü yönetimi", "UI", "Index", "Font"], 0, "Structured.")
                elif cat == "testing":
                    if k == 0:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Arrange-Act-Assert nedir?", ["Test yapısı", "UI", "SQL", "Font"], 0, "AAA.")
                    elif k == 1:
                        add(out_med, "medium", "tf", f"[{ln} • {tt}] Flaky test kararsız testtir.", None, True, "Flaky.")
                    elif k == 2:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Test izolasyonu neden önemlidir?", ["Deterministik sonuç", "UI", "Index", "Font"], 0, "Isolation.")
                    elif k == 3:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Mock ne zaman gerekir?", ["Dış bağımlılığı taklit", "UI", "Font", "Index"], 0, "Mock.")
                    elif k == 4:
                        add(out_med, "medium", "tf", f"[{ln} • {tt}] Coverage %100 olması kalite garantisi değildir.", None, True, "Coverage.")
                    elif k == 5:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Regression test neyi yakalar?", ["Eski bug'ın geri gelmesi", "UI", "Index", "Font"], 0, "Regression.")
                    elif k == 6:
                        add(out_med, "medium", "fill", f"[{ln} • {tt}] Birim test türü: ______ test", "unit", None, "Unit.")
                    else:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Assertion ne yapar?", ["Bekleneni doğrular", "UI", "SQL", "Font"], 0, "Assert.")
                elif cat == "sql":
                    if k == 0:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] LEFT JOIN'de eşleşmeyen sağ kolonlar ne olur?", ["NULL", "0", "hata", "boş string"], 0, "LEFT JOIN.")
                    elif k == 1:
                        add(out_med, "medium", "tf", f"[{ln} • {tt}] JOIN koşulu yanlış yazılırsa satırlar patlayabilir.", None, True, "Cartesian.")
                    elif k == 2:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Index hangi trade-off'u getirir?", ["Yazma maliyeti", "UI", "Font", "Thread"], 0, "Index trade-off.")
                    elif k == 3:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Transaction ne sağlar?", ["Atomiklik", "UI", "Font", "Thread"], 0, "ACID.")
                    elif k == 4:
                        add(out_med, "medium", "fill", f"[{ln} • {tt}] NULL kontrolü için: IS ______", "NULL", None, "IS NULL.")
                    elif k == 5:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] GROUP BY ile hangi fonksiyon sık kullanılır?", ["COUNT/SUM", "PRINT", "IMPORT", "CALL"], 0, "Aggregates.")
                    elif k == 6:
                        add(out_med, "medium", "tf", f"[{ln} • {tt}] WHERE, GROUP BY'dan önce çalışır (genel mantık).", None, True, "Logical order.")
                    else:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] ORDER BY ne yapar?", ["Sıralar", "Filtreler", "Gruplar", "Join"], 0, "Sort.")
                elif cat == "memory":
                    if k == 0:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Double free ne demektir?", ["Aynı belleği iki kez serbest bırakmak", "UI", "SQL", "Font"], 0, "Double free.")
                    elif k == 1:
                        add(out_med, "medium", "tf", f"[{ln} • {tt}] Dangling pointer kullanımı UB/crash üretebilir.", None, True, "Danger.")
                    elif k == 2:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Heap vs stack farkı?", ["Ömür/yönetim", "UI", "SQL", "Font"], 0, "Memory.")
                    elif k == 3:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Buffer overflow riski nereden gelir?", ["Sınır kontrolü olmaması", "UI", "Index", "Font"], 0, "Overflow.")
                    elif k == 4:
                        add(out_med, "medium", "tf", f"[{ln} • {tt}] Pointer aritmetiği dikkat gerektirir.", None, True, "Pointer math.")
                    elif k == 5:
                        add(out_med, "medium", "fill", f"[{ln} • {tt}] Null pointer kontrolü: if (p == ______)", null_word, None, "Null check.")
                    elif k == 6:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Memory leak nasıl oluşur?", ["Serbest bırakmayı unutmak", "UI", "SQL", "Font"], 0, "Leak.")
                    else:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Undefined behavior ne demektir?", ["Sonuç garanti değil", "UI", "SQL", "Font"], 0, "UB.")
                else:
                    # advanced
                    if k == 0:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] '{kw1}' ile ilgili doğru yaklaşım hangisidir?", ["Kanıt/örnek ile doğrulamak", "Ezber", "UI", "Font"], 0, "Keyword reasoning.")
                    elif k == 1:
                        add(out_med, "medium", "tf", f"[{ln} • {tt}] Bu konu genelde birden fazla alt kavram içerir.", None, True, "Advanced.")
                    elif k == 2:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Debug/build/perf üçlüsünden hangisi bu konu için daha olası?", ["Hepsi", "UI", "Font", "Renk"], 0, "Advanced.")
                    elif k == 3:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] 'trade-off' ne demektir?", ["Artı/eksi dengesi", "UI", "Index", "Thread"], 0, "Trade-off.")
                    elif k == 4:
                        add(out_med, "medium", "tf", f"[{ln} • {tt}] Yanlış optimizasyon bazı durumlarda performansı düşürebilir.", None, True, "Perf.")
                    elif k == 5:
                        add(out_med, "medium", "fill", f"[{ln} • {tt}] Bu konudan bir anahtar kelime: ______", kw2, None, "Keyword.")
                    elif k == 6:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Hata ayıklamada en iyi başlangıç hangisi?", ["İlk hatayı çözmek", "Rastgele", "UI", "Font"], 0, "Debug.")
                    else:
                        add(out_med, "medium", "mcq", f"[{ln} • {tt}] Performans darboğazı nedir?", ["En yavaş nokta", "UI", "SQL", "Font"], 0, "Bottleneck.")

            # HARD: scenario + trick options; still topic-specific
            for i in range(1, 9999):
                if len(out_hard) >= target_per_diff:
                    break
                k = (i - 1) % 8
                if cat == "control":
                    n = 20 + (i % 30)
                    if k == 0:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] 1..{n} arası hem 3'e hem 5'e bölünen kaç sayı var?", [str(n//15), str((n+14)//15), "0", str(n//5)], 0, "LCM=15.")
                    elif k == 1:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Koşul/loop hataları çoğu zaman edge-case'te çıkar.", None, True, "Edge-case.")
                    elif k == 2:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Sonsuz döngüye en yakın senaryo hangisi?", ["Koşul değişmiyor", "Yorum var", "UI", "Index"], 0, "Infinite loop.")
                    elif k == 3:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] break yanlış yerde kullanılırsa ne olur?", ["Erken çıkar", "UI", "SQL", "Font"], 0, "Flow.")
                    elif k == 4:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] continue neyi atlar?", ["O iterasyonun kalanını", "UI", "SQL", "Font"], 0, "Continue.")
                    elif k == 5:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Off-by-one, test edilmezse fark edilmesi zor bir hatadır.", None, True, "Tricky.")
                    elif k == 6:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Switch fallthrough riski ne zaman olur?", ["break yoksa", "UI", "Index", "Font"], 0, "Fallthrough.")
                    else:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Koşul ifadesinde en tehlikeli hata hangisi?", ["Atama/karşılaştırma karışması", "Yorum", "UI", "Font"], 0, "Operator.")
                elif cat == "functions":
                    if k == 0:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Yan etki (side effect) test etmeyi zorlaştırabilir.", None, True, "Side effect.")
                    elif k == 1:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Global state'e bağımlı fonksiyonun sorunu?", ["Deterministik değil", "UI", "SQL", "Font"], 0, "Global state.")
                    elif k == 2:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Recursion için en kritik risk?", ["Stack overflow", "UI", "Index", "Font"], 0, "Recursion.")
                    elif k == 3:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Çok parametreli fonksiyon okunabilirliği düşürebilir.", None, True, "Params.")
                    elif k == 4:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] API breaking change hangisidir?", ["İmza değişimi", "Yorum", "UI", "Renk"], 0, "Signature.")
                    elif k == 5:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] En iyi refactor yaklaşımı?", ["Test + küçük adımlar", "Sil + yaz", "UI", "Font"], 0, "Safe refactor.")
                    elif k == 6:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Fonksiyon adı davranışı yansıtmalıdır.", None, True, "Naming.")
                    else:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Lambda/closure ne sağlar?", ["Fonksiyonu değer gibi kullanma", "UI", "SQL", "Font"], 0, "Closures.")
                elif cat == "collections":
                    if k == 0:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] HashMap worst-case karmaşıklık artabilir mi?", ["Evet", "Hayır", "UI", "Font"], 0, "Worst-case.")
                    elif k == 1:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Stable sort her dilde default değildir.", None, True, "Sorting.")
                    elif k == 2:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Iterator invalidation ne demektir?", ["Geçersiz iterator", "UI", "SQL", "Font"], 0, "Iterators.")
                    elif k == 3:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Büyük veri için en iyi yaklaşım?", ["Streaming/iterator", "Hepsini RAM", "UI", "Font"], 0, "Streaming.")
                    elif k == 4:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Mutable/immutable farkı bug riskini etkileyebilir.", None, True, "Mutability.")
                    elif k == 5:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Map key equality için en kritik şey?", ["Hash/equals doğru", "UI", "Font", "Renk"], 0, "Hash.")
                    elif k == 6:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Set hangi durumda yanlış seçim olur?", ["Sıra gerekiyorsa", "Unique gerekiyorsa", "UI", "Font"], 0, "Order.")
                    else:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Dizi index hataları çoğu zaman sınır değerle yakalanır.", None, True, "Edge-case.")
                elif cat == "string":
                    if k == 0:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Unicode grapheme nedir?", ["Birden çok codepoint tek karakter", "UI", "SQL", "Font"], 0, "Unicode.")
                    elif k == 1:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] String slicing bazı dillerde O(n) olabilir.", None, True, "Complexity.")
                    elif k == 2:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Regex performans riski hangisidir?", ["Catastrophic backtracking", "UI", "SQL", "Font"], 0, "Regex.")
                    elif k == 3:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Locale-sensitive case dönüşümü sorun yaratabilir mi?", ["Evet", "Hayır", "UI", "Font"], 0, "Locale.")
                    elif k == 4:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] String karşılaştırmasında normalize gerekebilir.", None, True, "Normalization.")
                    elif k == 5:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Immutable string'in avantajı?", ["Thread-safety", "UI", "SQL", "Font"], 0, "Immutable.")
                    elif k == 6:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Format string injection riski hangi durumda olur?", ["Kontrolsüz format", "UI", "Index", "Font"], 0, "Injection.")
                    else:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] String encode/decode hataları veri kaybı yaratabilir.", None, True, "Encoding.")
                elif cat == "files":
                    if k == 0:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Dosya yazmada data kaybı riski?", ["Flush/close unutmak", "UI", "SQL", "Font"], 0, "Flush.")
                    elif k == 1:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Atomic write için geçici dosya + rename yaklaşımı kullanılabilir.", None, True, "Atomic write.")
                    elif k == 2:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] CSV parse ederken en sık tuzak?", ["Delimiter/quote", "UI", "Index", "Font"], 0, "CSV.")
                    elif k == 3:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Path traversal riski nedir?", ["../ ile kaçış", "UI", "SQL", "Font"], 0, "Security.")
                    elif k == 4:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Dosya okuma IO-bound bir iştir.", None, True, "IO-bound.")
                    elif k == 5:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Binary dosya ile text dosya farkı?", ["Encoding", "UI", "Font", "Renk"], 0, "Binary/text.")
                    elif k == 6:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Büyük dosyayı memory-map etmek bazı durumlarda avantajlı olabilir.", None, True, "mmap.")
                    else:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] File descriptor leak nasıl olur?", ["Close unutmak", "UI", "SQL", "Font"], 0, "FD leak.")
                elif cat == "errors":
                    if k == 0:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Exception swallowing neden kötü?", ["Bug gizler", "UI", "Font", "Index"], 0, "Swallow.")
                    elif k == 1:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Hata log'u kişisel veri sızdırabilir; dikkat gerekir.", None, True, "PII.")
                    elif k == 2:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Retry her hatada doğru mu?", ["Hayır, idempotency gerekir", "Evet", "UI", "Font"], 0, "Retry.")
                    elif k == 3:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Null dereference hangi kategoriye girer?", ["Runtime error", "Syntax", "UI", "Font"], 0, "Runtime.")
                    elif k == 4:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Exception mesajı kullanıcıya doğrudan gösterilmemelidir (güvenlik).", None, True, "Security.")
                    elif k == 5:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Stack trace production'da risk mi?", ["Evet, bilgi sızdırabilir", "Hayır", "UI", "Font"], 0, "Leak.")
                    elif k == 6:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] En iyi hata mesajı nasıl olmalı?", ["Eylem önerir", "Kaba", "UI", "Font"], 0, "DX.")
                    else:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Exception türlerini sınıflamak (IO/parse/logic) çözümü hızlandırır.", None, True, "分类.")
                elif cat == "oop":
                    if k == 0:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Liskov Substitution neyi söyler?", ["Alt sınıf üst sınıf yerine geçebilmeli", "UI", "SQL", "Font"], 0, "LSP.")
                    elif k == 1:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Diamond problem bazı inheritance tasarımlarında ortaya çıkar.", None, True, "Inheritance.")
                    elif k == 2:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Composition over inheritance ne demektir?", ["Kalıtım yerine bileşim tercih", "UI", "SQL", "Font"], 0, "Design.")
                    elif k == 3:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Interface segregation neyi hedefler?", ["Küçük arayüzler", "UI", "SQL", "Font"], 0, "ISP.")
                    elif k == 4:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Dependency inversion, test edilebilirliği artırır.", None, True, "DIP.")
                    elif k == 5:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Virtual dispatch maliyeti olabilir mi?", ["Evet", "Hayır", "UI", "Font"], 0, "Dispatch.")
                    elif k == 6:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Abstract class vs interface farkı?", ["State + default impl olabilir", "UI", "SQL", "Font"], 0, "OOP.")
                    else:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Over-engineering, gereksiz soyutlama demektir.", None, True, "Design.")
                elif cat == "async":
                    if k == 0:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Concurrency vs parallelism farkı?", ["Aynı değildir", "Aynıdır", "UI", "Font"], 0, "Concept.")
                    elif k == 1:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Shared mutable state race riskini artırır.", None, True, "Race.")
                    elif k == 2:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Backpressure ne demektir?", ["Üretici hızını sınırlama", "UI", "SQL", "Font"], 0, "Streams.")
                    elif k == 3:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Cancellation neden önemli?", ["Kaynakları bırakmak", "UI", "Index", "Font"], 0, "Cancel.")
                    elif k == 4:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Timeout ayarı yanlışsa false negative/positive olur.", None, True, "Timeout.")
                    elif k == 5:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Thread-safe ne demektir?", ["Eşzamanlı kullanım güvenli", "UI", "SQL", "Font"], 0, "Thread-safe.")
                    elif k == 6:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Deadlock çözümü için hangisi?", ["Lock ordering", "UI", "SQL", "Font"], 0, "Ordering.")
                    else:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Async hata yönetimi için try/catch/.catch gerekir.", None, True, "Errors.")
                elif cat == "testing":
                    if k == 0:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Flaky test'in en büyük problemi?", ["Güven kaybı", "UI", "SQL", "Font"], 0, "Flaky.")
                    elif k == 1:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Deterministik testler için time/random kontrol edilmeli.", None, True, "Determinism.")
                    elif k == 2:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Property-based testing neyi hedefler?", ["Özellikleri rastgele doğrulamak", "UI", "Index", "Font"], 0, "PBT.")
                    elif k == 3:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Snapshot test riski?", ["Gereksiz güncellemeler", "UI", "SQL", "Font"], 0, "Snapshot.")
                    elif k == 4:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Mock aşırı kullanılırsa testler kırılgan olur.", None, True, "Over-mocking.")
                    elif k == 5:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Integration test'in maliyeti?", ["Daha yavaş", "UI", "Font", "Renk"], 0, "Cost.")
                    elif k == 6:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] TDD'nin amacı?", ["Önce test sonra kod", "UI", "SQL", "Font"], 0, "TDD.")
                    else:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] CI üzerinde testler çalıştırmak regresyonu yakalar.", None, True, "CI.")
                elif cat == "sql":
                    if k == 0:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Transaction isolation neyi etkiler?", ["Tutarlılık", "UI", "Font", "Renk"], 0, "Isolation.")
                    elif k == 1:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Phantom read bazı isolation seviyelerinde görülebilir.", None, True, "Phantom.")
                    elif k == 2:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Window function ne sağlar?", ["Satır üstü aggregate", "UI", "Index", "Font"], 0, "Window.")
                    elif k == 3:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] N+1 sorgu problemi nerede görülür?", ["ORM", "UI", "Font", "Renk"], 0, "N+1.")
                    elif k == 4:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] EXPLAIN plan okumak performansı anlamaya yardım eder.", None, True, "Explain.")
                    elif k == 5:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Covering index ne demektir?", ["Sorgu kolonlarını kapsayan index", "UI", "Font", "Renk"], 0, "Covering.")
                    elif k == 6:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Çok index bazen daha yavaş yazma demektir.", None, True, "Trade-off.")
                    else:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Deadlock SQL'de mümkün mü?", ["Evet", "Hayır", "UI", "Font"], 0, "DB deadlock.")
                elif cat == "memory":
                    if k == 0:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Use-after-free ne demektir?", ["Serbest sonrası kullanmak", "UI", "SQL", "Font"], 0, "UAF.")
                    elif k == 1:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Static analysis bazı bellek hatalarını yakalayabilir.", None, True, "Static.")
                    elif k == 2:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Stack overflow ne zaman olur?", ["Derin recursion", "UI", "SQL", "Font"], 0, "Stack.")
                    elif k == 3:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] ASLR neyi zorlaştırır?", ["Exploit", "UI", "Font", "Renk"], 0, "Security.")
                    elif k == 4:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Undefined behavior debug'ı zorlaştırır.", None, True, "UB.")
                    elif k == 5:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Valgrind benzeri araç ne içindir?", ["Leak tespiti", "UI", "SQL", "Font"], 0, "Tools.")
                    elif k == 6:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Buffer overflow'un en büyük riski?", ["Güvenlik açığı", "UI", "Font", "Renk"], 0, "Security.")
                    else:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Pointer aritmetiği sınır kontrolü olmadan tehlikelidir.", None, True, "Safety.")
                else:
                    # advanced
                    if k == 0:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] '{kw1}' ile ilgili yanlış olan hangisi?", ["Bu konu ile ilgisiz UI", "Bu konu ile ilgili olabilir", "Bu konu ile ilgili olabilir", "Bu konu ile ilgili olabilir"], 0, "Keyword.")
                    elif k == 1:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Performans/Debug/Build konuları genelde trade-off içerir.", None, True, "Trade-off.")
                    elif k == 2:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] En doğru yaklaşım hangisi?", ["Kanıtla, sonra değiştir", "Rastgele", "UI", "Font"], 0, "Evidence.")
                    elif k == 3:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Bottleneck ne demektir?", ["En yavaş nokta", "UI", "SQL", "Font"], 0, "Bottleneck.")
                    elif k == 4:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Cache yanlışsa stale data üretebilir.", None, True, "Cache.")
                    elif k == 5:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Debug build vs release farkı?", ["Optimizasyon/semboller", "UI", "Font", "Renk"], 0, "Build modes.")
                    elif k == 6:
                        add(out_hard, "hard", "tf", f"[{ln} • {tt}] Logging aşırı olursa performansı etkileyebilir.", None, True, "Logging.")
                    else:
                        add(out_hard, "hard", "mcq", f"[{ln} • {tt}] Observability neyi kapsar?", ["Log+metric+trace", "UI", "Font", "Renk"], 0, "Observability.")

        def pad_to_target(diff: str, out_list: list[dict]):
            # If templates+code blocks are insufficient, pad with keyword-driven,
            # topic-specific but varied questions (not just numeric variations).
            if len(out_list) >= target_per_diff:
                return

            # Build a pool of prompt patterns that differ structurally.
            kws2 = [kw1, kw2, kw3, tt]
            kws2 = [k for k in kws2 if k]
            if not kws2:
                kws2 = [tt or "konu"]

            anchors = LANG_ANCHORS.get(lid) or {}
            null_word = anchors.get("null", "null")

            patterns: list[tuple[str, str]] = []
            if diff == "easy":
                patterns = [
                    ("mcq", "Aşağıdakilerden hangisi '{k}' ile en çok ilişkilidir?"),
                    ("tf", "'{k}' bu konunun temel kavramlarından biridir."),
                    ("mcq", "'{k}' genelde neyi ifade eder?"),
                    ("fill", "'{k}' için anahtar kelime/terim: ______"),
                    ("mcq", "Bu konuda en sık karşılaşılan hata hangisine benzer?"),
                    ("mcq", "Bu konu hangi hedefe hizmet eder?"),
                    ("tf", "Bu konu öğrenildikten sonra küçük örneklerle pratik yapmak faydalıdır."),
                    ("mcq", "'{k}' ile ilgili doğru ifade hangisidir?"),
                    ("mcq", "'{k}' hangi bağlamda kullanılır?"),
                    ("tf", "'{k}' yanlış anlaşılırsa karışıklık oluşabilir."),
                    ("mcq", "Bu konuyu öğrenirken ilk adım hangisidir?"),
                    ("mcq", "'{k}' ile ilgili örnek hangisine benzer?"),
                    ("fill", "Bu konunun anahtar terimlerinden biri: ______"),
                    ("mcq", "'{k}' için en iyi tanım hangisidir?"),
                    ("tf", "Bu konuda temel kavramları bilmek ileride işini kolaylaştırır."),
                    ("mcq", "Bu konu hangi problem sınıfını çözer?"),
                    ("mcq", "'{k}' ile en çok karıştırılan kavram hangisidir?"),
                    ("fill", "'{k}' ile birlikte sık geçen ikinci terim: ______"),
                    ("mcq", "'{k}' hangi kategoriye daha yakındır?"),
                    ("tf", "Bu konu, programın davranışını değiştirebilir/etkileyebilir."),
                    ("mcq", "Bu konu hangi beceriyi geliştirir?"),
                    ("mcq", "'{k}' ile ilgili en basit doğrulama hangisidir?"),
                    ("fill", "Bu konuda sık geçen bir terim: ______"),
                    ("mcq", "'{k}' hangi tür hata ile ilişkilendirilebilir?"),
                ]
            elif diff == "medium":
                patterns = [
                    ("mcq", "'{a}' ve '{b}' arasındaki fark hangisine en yakındır?"),
                    ("tf", "'{k}' yanlış kullanılırsa hata/bug oluşabilir."),
                    ("mcq", "'{k}' için en güvenli yaklaşım hangisidir?"),
                    ("mcq", "Edge-case hangisidir?"),
                    ("fill", "'{k}' ile ilgili kritik kontrol: ______"),
                    ("mcq", "Aşağıdakilerden hangisi '{k}' için doğru örnektir?"),
                    ("mcq", "'{k}' kullanırken hangi kontrol yapılmalıdır?"),
                    ("tf", "'{k}' ile ilgili hatalar genelde belirli senaryolarda görünür."),
                    ("mcq", "'{k}' ile ilgili risk hangisidir?"),
                    ("mcq", "'{k}' için en iyi pratik hangisidir?"),
                    ("fill", "'{k}' kullanırken dikkat edilmesi gereken: ______"),
                    ("mcq", "Şu senaryoda '{k}' doğru mu? (en yakın seçenek)"),
                    ("mcq", "'{k}' ile ilgili yanlış yaklaşım hangisidir?"),
                    ("tf", "Bu konuda edge-case test etmek önemlidir."),
                    ("mcq", "'{k}' hangi durumda beklenmedik sonuç üretir?"),
                    ("fill", "Bu konuyla ilgili yaygın hata türü: ______"),
                    ("mcq", "'{k}' ile ilgili doğru/yanlış ayrımı hangisidir?"),
                    ("mcq", "Bu konu için 'trade-off' örneği hangisidir?"),
                    ("tf", "Bu konuyu sağlamlaştırmak için küçük testler faydalıdır."),
                    ("mcq", "'{k}' ile ilgili en yaygın tuzak hangisidir?"),
                ]
            else:  # hard
                patterns = [
                    ("mcq", "Bir kodda '{k}' ile ilgili bug varsa en olası sebep hangisi?"),
                    ("tf", "Bu konuda performans/sağlamlık trade-off'u olabilir."),
                    ("mcq", "'{k}' ile ilgili en tehlikeli tuzak hangisidir?"),
                    ("mcq", "Aşağıdaki senaryolardan hangisi '{k}' açısından daha riskli?"),
                    ("fill", "'{k}' için en kritik prensip: ______"),
                    ("mcq", "'{k}' kaynaklı bir hata üretmemek için en iyi strateji hangisi?"),
                    ("tf", "Bu konuda küçük bir hata büyük bir bug'a dönüşebilir."),
                    ("mcq", "'{k}' ile ilgili hatayı debug ederken ilk bakılacak yer hangisi?"),
                    ("mcq", "'{k}' ile ilgili güvenlik riski hangisidir?"),
                    ("fill", "Bu konuda en kritik kontrol mekanizması: ______"),
                    ("mcq", "'{k}' ile ilgili performans darboğazı hangi durumda olur?"),
                    ("tf", "Bu konu bazı dillerde farklı kurallara sahip olabilir."),
                    ("mcq", "'{k}' ile ilgili hatayı azaltan tasarım hangisidir?"),
                    ("mcq", "'{k}' yanlış yönetilirse hangi sonuç çıkar?"),
                    ("fill", "'{k}' için en kritik kural: ______"),
                ]

            # Choices banks (topic-aligned distractors)
            def choices_for(k: str) -> list[str]:
                base = [k, kw2, kw3, "UI", "donanım", "network", "dosya", null_word]
                # Keep non-empty unique
                seen = set()
                outc = []
                for x in base:
                    x = str(x)
                    if not x.strip() or x in seen:
                        continue
                    seen.add(x)
                    outc.append(x)
                return outc[:4] if len(outc) >= 4 else (outc + ["diğer"] * 4)[:4]

            i = 0
            guard = 0
            while len(out_list) < target_per_diff and guard < 2000:
                guard += 1
                k = kws2[i % len(kws2)]
                a = kws2[(i + 1) % len(kws2)]
                b = kws2[(i + 2) % len(kws2)]
                typ, fmt = patterns[i % len(patterns)]
                prompt = f"[{ln} • {tt}] " + fmt.format(k=k, a=a, b=b)

                if typ == "tf":
                    add(out_list, diff, "tf", prompt, None, True, "Konuya özel doğrulama sorusu.")
                elif typ == "fill":
                    # Use k itself as the expected fill to avoid nonsense.
                    add(out_list, diff, "fill", prompt, k, None, "Bu konuda anahtar terim.")
                else:
                    ch = choices_for(k)
                    # ensure k is first and answerIndex=0
                    if ch[0] != k:
                        if k in ch:
                            ch.remove(k)
                        ch = [k] + ch
                        ch = ch[:4]
                    add(out_list, diff, "mcq", prompt, ch, 0, "Bu konuda anahtar terimi seç.")
                i += 1

            # Last resort: ensure we always hit the requested count using
            # varied, non-numeric hint phrases (still topic-keyword bound).
            if len(out_list) < target_per_diff:
                hints = [
                    "kısa tanım", "örnek kullanım", "hata senaryosu", "kural", "istisna",
                    "pratik", "risk", "güvenlik", "performans", "okunabilirlik",
                    "edge-case", "doğrulama", "yanlış kullanım", "doğru yaklaşım", "trade-off",
                    "kısıt", "sınır", "uygulama", "mantık", "kontrol",
                    "sonuç", "davranış", "beklenti", "tuzak", "ipuçları",
                ]
                j = 0
                while len(out_list) < target_per_diff and j < len(hints) * 4:
                    hint = hints[j % len(hints)]
                    k = kws2[j % len(kws2)]
                    prompt = f"[{ln} • {tt}] '{k}' ile ilgili en doğru seçenek hangisi? (İpucu: {hint})"
                    ch = choices_for(k)
                    if ch and ch[0] != k:
                        if k in ch:
                            ch.remove(k)
                        ch = [k] + ch
                        ch = ch[:4]
                    add(out_list, diff, "mcq", prompt, ch, 0, "Konuya özel pekiştirme sorusu.")
                    j += 1

        easy: list[dict] = []
        med: list[dict] = []
        hard: list[dict] = []
        add_from_code(easy, med, hard)
        fill_templates(easy, med, hard)
        pad_to_target("easy", easy)
        pad_to_target("medium", med)
        pad_to_target("hard", hard)

        # Hard stop: enforce exact sizes.
        return easy[:target_per_diff] + med[:target_per_diff] + hard[:target_per_diff]

    def _mcq(diff: str, prompt: str, choices: list[str], ans: int, exp: str):
        return ("mcq", diff, prompt, choices, ans, exp)

    def _tf(diff: str, prompt: str, ans: bool, exp: str):
        return ("tf", diff, prompt, None, ans, exp)

    def _fill(diff: str, prompt: str, answer_text: str, exp: str):
        return ("fill", diff, prompt, answer_text, None, exp)

    # Language-specific anchors so every language gets different, relevant questions.
    # These are intentionally "quiz" questions (not code execution) but tied to the language's syntax & semantics.
    LANG_ANCHORS: dict[str, dict[str, str]] = {
        "python": {"func": "def", "null": "None", "bool_true": "True", "bool_false": "False", "comment": "#"},
        "javascript": {"func": "function", "null": "null", "bool_true": "true", "bool_false": "false", "comment": "//"},
        "typescript": {"func": "function", "null": "null", "bool_true": "true", "bool_false": "false", "comment": "//"},
        "dart": {"func": "void", "null": "null", "bool_true": "true", "bool_false": "false", "comment": "//"},
        "java": {"func": "static", "null": "null", "bool_true": "true", "bool_false": "false", "comment": "//"},
        "c": {"func": "int", "null": "NULL", "bool_true": "1", "bool_false": "0", "comment": "//"},
        "cpp": {"func": "int", "null": "nullptr", "bool_true": "true", "bool_false": "false", "comment": "//"},
        "go": {"func": "func", "null": "nil", "bool_true": "true", "bool_false": "false", "comment": "//"},
        "rust": {"func": "fn", "null": "None", "bool_true": "true", "bool_false": "false", "comment": "//"},
        "php": {"func": "function", "null": "null", "bool_true": "true", "bool_false": "false", "comment": "//"},
        "ruby": {"func": "def", "null": "nil", "bool_true": "true", "bool_false": "false", "comment": "#"},
        "swift": {"func": "func", "null": "nil", "bool_true": "true", "bool_false": "false", "comment": "//"},
        "kotlin": {"func": "fun", "null": "null", "bool_true": "true", "bool_false": "false", "comment": "//"},
        "r": {"func": "function", "null": "NULL", "bool_true": "TRUE", "bool_false": "FALSE", "comment": "#"},
        "matlab": {"func": "function", "null": "[]", "bool_true": "true", "bool_false": "false", "comment": "%"},
        "sql": {"func": "SELECT", "null": "NULL", "bool_true": "TRUE", "bool_false": "FALSE", "comment": "--"},
    }
    a = LANG_ANCHORS.get(lid) or LANG_ANCHORS.get("javascript")  # safe fallback

    # Per-language base bank (makes languages diverge even for same flags/topics).
    base_bank: list[tuple] = []
    if lid == "python":
        base_bank += [
            _mcq("easy", "Python'da blok yapısı genelde ne ile belirlenir?", ["Girinti (indentation)", "Süslü parantez {}", "BEGIN/END", "Noktalı virgül ;"], 0, "Python blokları girintiyle belirler."),
            _mcq("easy", "Python'da boş değer/sentinel olarak en çok hangisi kullanılır?", ["None", "null", "nil", "NULL"], 0, "Python'da boş değerin karşılığı None'dır."),
            _tf("medium", "Python'da list ve dict gibi yapılar mutable (değiştirilebilir) olabilir.", True, "List/dict mutable'dır; tuple gibi yapılar immutable olabilir."),
            _mcq("hard", "Python'da `==` ile `is` arasındaki fark için en doğru ifade hangisidir?", ["== değer eşitliği, is kimlik (aynı nesne) kontrolü", "İkisi tamamen aynıdır", "is daha hızlı olduğundan her zaman tercih edilir", "== sadece stringlerde çalışır"], 0, "`is` aynı objeyi mi gösteriyor diye bakar."),
        ]
    elif lid in ("javascript", "typescript"):
        base_bank += [
            _mcq("easy", "JavaScript'te değişken tanımlamak için hangileri kullanılır?", ["let/const/var", "def", "int", "val"], 0, "JS'de let/const/var vardır."),
            _mcq("medium", "JS'de `==` yerine çoğu zaman hangisi önerilir?", ["===", "=", "=>", "!=="], 0, "=== tip dönüşümü yapmadan karşılaştırır."),
            _tf("medium", "JavaScript'te `const` ile tanımlanan bir objenin iç alanları değiştirilebilir.", True, "const referansı sabitler; objenin içeriği değişebilir."),
            _mcq("hard", "Promise zincirinde hatayı yakalamanın en genel yolu hangisidir?", [".catch(...)", "try/catch (await olmadan)", "console.log", "return;"], 0, "Promise hataları .catch ile yakalanabilir; async/await ile try/catch de olur."),
        ]
        if lid == "typescript":
            base_bank += [
                _mcq("easy", "TypeScript'in JS'e göre en belirgin farkı nedir?", ["Statik tip sistemi (type checking)", "Yeni bir runtime", "Tarayıcıya özel olması", "Sadece backend dili olması"], 0, "TS, JS üzerine tip sistemi ekler."),
                _tf("hard", "TypeScript'te `any` kullanımı tip güvenliğini ciddi azaltır.", True, "any, type checking'i büyük ölçüde devre dışı bırakır."),
            ]
    elif lid == "dart":
        base_bank += [
            _mcq("easy", "Dart'ta `final` ne ifade eder?", ["Değer bir kez atanır", "Her zaman null olur", "Sadece int olur", "Fonksiyon tanımlar"], 0, "final bir kez atanır."),
            _mcq("medium", "Dart'ta asenkron fonksiyonlar genelde ne döndürür?", ["Future", "Promise", "Thread", "Coroutine"], 0, "Dart async işleri Future ile temsil eder."),
            _tf("hard", "Dart'ta null-safety ile nullable tipler genelde `?` ile gösterilir.", True, "Örn: String?"),
        ]
    elif lid == "java":
        base_bank += [
            _mcq("easy", "Java'da programın giriş noktası genelde hangi metottur?", ["public static void main(String[] args)", "init()", "start()", "run()"], 0, "Java'nın entrypoint'i main'dir."),
            _tf("medium", "Java'da String nesneleri immutable'dır.", True, "String immutable tasarlanmıştır."),
            _mcq("hard", "Java'da checked exception ile ilgili doğru ifade hangisidir?", ["Bazıları try/catch veya throws ister", "Hiçbir zaman yakalanmaz", "Sadece runtime'da oluşur", "Sadece print ile çözülür"], 0, "Checked exception'lar derleme zamanında zorlar."),
        ]
    elif lid in ("c", "cpp"):
        base_bank += [
            _mcq("easy", "C/C++ kodunda satır sonlandırma için sık kullanılan karakter hangisidir?", [";", ":", ".", ","], 0, "İfadeler genelde ; ile biter."),
            _mcq("medium", "Pointer en doğru şekilde neyi temsil eder?", ["Bellek adresi", "Metin", "Ondalık sayı", "Sadece fonksiyon"], 0, "Pointer bir adres tutar."),
            _tf("hard", "C'de buffer overflow gibi hatalar güvenlik açığına dönüşebilir.", True, "Sınır kontrolü yapılmazsa bellek taşması olabilir."),
        ]
        if lid == "cpp":
            base_bank += [
                _mcq("medium", "C++'ta `new` ile ayrılan bellek genelde nasıl serbest bırakılır?", ["delete", "free", "gc()", "dispose()"], 0, "new/delete eşleşir (tercihen RAII)."),
            ]
    elif lid == "sql":
        base_bank += [
            _mcq("easy", "SQL'de tüm kolonları seçmek için hangi ifade kullanılır?", ["SELECT *", "GET ALL", "PICK *", "FETCH ALL"], 0, "SELECT * tüm kolonlardır."),
            _mcq("medium", "Gruplama yapmak için hangisi kullanılır?", ["GROUP BY", "ORDER BY", "WHERE", "LIMIT"], 0, "GROUP BY gruplar."),
            _tf("hard", "SQL'de NULL karşılaştırması `=` ile değil çoğunlukla `IS NULL` ile yapılır.", True, "NULL özel bir değerdir."),
        ]
    else:
        # Other languages: still language-specific tokens so they don't become identical.
        base_bank += [
            _mcq("easy", f"{ln} dilinde fonksiyon tanımlama için tipik anahtar kelime hangisine daha yakındır?", [a["func"], "class", "package", "import"], 0, "Dil ailesine göre fonksiyon anahtar kelimesi değişir."),
            _mcq("medium", f"{ln} dilinde 'boş değer' kavramına en yakın ifade hangisidir?", [a["null"], "zero", "empty", "undefined"], 0, "Her dilde boş değerin temsilcisi farklıdır."),
            _tf("hard", "Derleyici/yorumlayıcı hatalarında ilk hatayı çözmek, diğer hataların çoğunu otomatik yok edebilir.", True, "Hata zinciri yaygındır."),
        ]

    # Topic-specific deep banks (keyed by topic id). These make questions truly "about the topic",
    # not just generic programming concepts.
    def topic_bank() -> list[tuple]:
        b: list[tuple] = []

        # --- PYTHON ---
        if lid == "python":
            if tid in ("py-degiskenler", "py-kurulum"):
                b += [
                    _mcq(
                        "easy",
                        "Python'da değişken tanımlamak için hangi anahtar kelime zorunludur?",
                        ["Hiçbiri (doğrudan atama yapılır)", "var", "let", "int"],
                        0,
                        "Python'da `x = 3` gibi doğrudan atama yapılır.",
                    ),
                    _mcq(
                        "medium",
                        "Aşağıdakilerden hangisi geçerli bir Python isimlendirmesidir?",
                        ["user_name", "2user", "user-name", "user name"],
                        0,
                        "Değişken adı rakamla başlayamaz ve boşluk/eksi içermez.",
                    ),
                    _mcq(
                        "hard",
                        "Python'da `x = x + 1` satırı çalışmadan önce x tanımlı değilse ne olur?",
                        ["NameError", "SyntaxError", "TypeError", "Hiçbir şey olmaz"],
                        0,
                        "Tanımsız isim kullanımı NameError üretir.",
                    ),
                ]

            if tid in ("py-kosul-dongu",):
                b += [
                    _mcq(
                        "easy",
                        "Python'da koşul bloğu başlatmak için satırın sonunda hangisi olmalıdır?",
                        [":", ";", "{", ")"],
                        0,
                        "if/for/while satırı `:` ile biter.",
                    ),
                    _mcq(
                        "medium",
                        "Bu kodun çıktısı nedir?\n\nfor i in range(3):\n    print(i)",
                        ["0\\n1\\n2", "1\\n2\\n3", "0\\n1\\n2\\n3", "2\\n1\\n0"],
                        0,
                        "range(3) 0,1,2 üretir.",
                    ),
                    _mcq(
                        "hard",
                        "Bu kod kaç kez 'x' yazdırır?\n\nfor i in range(1, 10, 3):\n    print('x')",
                        ["3", "4", "2", "5"],
                        0,
                        "1,4,7 → 3 kez.",
                    ),
                ]

            if tid in ("py-fonksiyonlar",):
                b += [
                    _mcq(
                        "easy",
                        "Python'da fonksiyon tanımlamak için hangi anahtar kelime kullanılır?",
                        ["def", "function", "fun", "fn"],
                        0,
                        "Python'da `def` kullanılır.",
                    ),
                    _mcq(
                        "medium",
                        "Aşağıdaki fonksiyon çağrısı ne yazdırır?\n\ndef add(a,b):\n    return a+b\n\nprint(add(2,3))",
                        ["5", "23", "0", "None"],
                        0,
                        "Toplama 5 eder.",
                    ),
                    _tf(
                        "hard",
                        "Python'da `return` yazılmadıysa fonksiyon varsayılan olarak None döndürür.",
                        True,
                        "Return yoksa None döner.",
                    ),
                ]

            if tid in ("py-koleksiyonlar",):
                b += [
                    _mcq(
                        "easy",
                        "Python'da sözlük (dict) literal'i hangisidir?",
                        ["{'a': 1}", "['a': 1]", "('a': 1)", "<a:1>"],
                        0,
                        "Dict süslü parantez ile yazılır.",
                    ),
                    _mcq(
                        "medium",
                        "Bu kod ne yazdırır?\n\nd = {'a':2,'b':1}\nprint(d.get('c', 0))",
                        ["0", "None", "KeyError", "1"],
                        0,
                        "get default ile 0 döner.",
                    ),
                    _mcq(
                        "hard",
                        "List comprehension aşağıdakilerden hangisini üretir?\n\n[n*n for n in [1,2,3] if n%2==1]",
                        ["[1, 9]", "[1, 4, 9]", "[4]", "[2, 6]"],
                        0,
                        "Tek sayılar 1 ve 3 → kareleri 1 ve 9.",
                    ),
                ]

            if tid in ("py-hatalar",):
                b += [
                    _mcq(
                        "easy",
                        "Python'da hata yakalama için hangi yapı kullanılır?",
                        ["try/except", "catch/throw", "guard", "rescue/ensure"],
                        0,
                        "Python try/except kullanır.",
                    ),
                    _mcq(
                        "medium",
                        "Aşağıdakilerden hangisi daha doğrudur?",
                        ["Önce spesifik exception, sonra genel Exception", "Önce Exception, sonra spesifik", "Except kullanmak gereksiz", "Try her zaman boştur"],
                        0,
                        "Spesifik olanlar önce yazılır.",
                    ),
                    _tf(
                        "hard",
                        "Bare `except:` (tür belirtmeden) genelde önerilmez.",
                        True,
                        "Çok geniş yakalar; hata ayıklamayı zorlaştırır.",
                    ),
                ]

            if tid in ("py-oop",):
                b += [
                    _mcq(
                        "easy",
                        "Python class içinde instance metodu ilk parametre olarak genelde ne alır?",
                        ["self", "this", "me", "cls"],
                        0,
                        "Instance metodu self alır.",
                    ),
                    _mcq(
                        "medium",
                        "Aşağıdaki kod ne yazdırır?\n\nclass A:\n    def __init__(self, x):\n        self.x = x\n\nprint(A(5).x)",
                        ["5", "A", "None", "x"],
                        0,
                        "x alanı 5 olur.",
                    ),
                    _tf(
                        "hard",
                        "Python'da `@classmethod` metodu ilk argüman olarak cls alır.",
                        True,
                        "classmethod sınıfı temsil eder.",
                    ),
                ]

        # --- JAVASCRIPT ---
        if lid == "javascript":
            if tid in ("js-tipler", "js-syntax"):
                b += [
                    _mcq(
                        "easy",
                        "JavaScript'te `typeof null` sonucu nedir?",
                        ["'object'", "'null'", "'undefined'", "'number'"],
                        0,
                        "Bu JS'nin tarihi bir davranışıdır.",
                    ),
                    _mcq(
                        "medium",
                        "Aşağıdakilerden hangisi `===` için doğrudur?",
                        ["Tip dönüşümü yapmaz", "Her zaman dönüşüm yapar", "Sadece sayılarda çalışır", "Sadece stringlerde çalışır"],
                        0,
                        "=== strict equality'dir.",
                    ),
                    _mcq(
                        "hard",
                        "Bu kod ne yazdırır?\n\nconsole.log('5' + 2)",
                        ["52", "7", "TypeError", "NaN"],
                        0,
                        "String + number → string birleştirme.",
                    ),
                ]
            if tid in ("js-async",):
                b += [
                    _mcq(
                        "easy",
                        "Promise hangi durumlardan hangisine sahip olabilir?",
                        ["pending/fulfilled/rejected", "start/stop/pause", "open/close", "true/false"],
                        0,
                        "Promise'in üç temel hali vardır.",
                    ),
                    _mcq(
                        "medium",
                        "Async fonksiyon ne döndürür?",
                        ["Promise", "number", "string", "void"],
                        0,
                        "async function her zaman Promise döndürür.",
                    ),
                    _tf(
                        "hard",
                        "await sadece async fonksiyon içinde kullanılabilir (module top-level hariç).",
                        True,
                        "Çoğu ortamda await için async gerekir.",
                    ),
                ]
            if tid in ("js-obj-array", "js-array-obj"):
                b += [
                    _mcq(
                        "easy",
                        "Array'in uzunluğu hangi property ile bulunur?",
                        ["length", "size", "count", "len"],
                        0,
                        "JS array length ile ölçülür.",
                    ),
                    _mcq(
                        "medium",
                        "Bu kodun çıktısı nedir?\n\nconsole.log([1,2,3].map(x=>x*2).join(','))",
                        ["2,4,6", "1,2,3", "3,2,1", "2 4 6"],
                        0,
                        "map ikiyle çarpar, join virgülle birleştirir.",
                    ),
                    _mcq(
                        "hard",
                        "Aşağıdakilerden hangisi `Array.prototype.reduce` için doğrudur?",
                        ["Bir diziyi tek değere indirger", "Sadece filtreler", "Sadece sıralar", "Sadece string'e çevirir"],
                        0,
                        "Reduce fold işlemi yapar.",
                    ),
                ]

        # --- JAVA ---
        if lid == "java":
            if tid in ("java-giris", "java-degiskenler"):
                b += [
                    _mcq(
                        "easy",
                        "Java'da boolean tipinin iki değeri hangileridir?",
                        ["true/false", "1/0", "yes/no", "T/F"],
                        0,
                        "Java boolean true/false alır.",
                    ),
                    _tf(
                        "medium",
                        "Java'da `int` primitive tiptir.",
                        True,
                        "Primitive tipler referans değildir.",
                    ),
                    _mcq(
                        "hard",
                        "Java'da `String` için doğru ifade hangisidir?",
                        ["immutable", "mutable", "pointer", "value type değil"],
                        0,
                        "String immutable'dır.",
                    ),
                ]
            if tid in ("java-kontrol-akisi",):
                b += [
                    _mcq(
                        "easy",
                        "Java'da switch yapısı genelde hangi tiplerle iyi çalışır?",
                        ["int/enum/String", "sadece float", "sadece boolean", "sadece array"],
                        0,
                        "Switch int/enum/String için yaygındır (sürüme göre).",
                    ),
                    _mcq(
                        "medium",
                        "Bu döngü kaç kez döner?\n\nfor(int i=0;i<5;i++){}",
                        ["5", "4", "6", "0"],
                        0,
                        "i=0..4 → 5 kez.",
                    ),
                    _tf(
                        "hard",
                        "Java'da `break` yazılmazsa switch-case fallthrough olabilir (klasik switch).",
                        True,
                        "Break yoksa alt case'e düşebilir.",
                    ),
                ]
            if tid in ("java-streams",):
                b += [
                    _mcq(
                        "easy",
                        "Stream API'nin temel fikri hangisidir?",
                        ["Veriyi pipeline ile dönüştürmek", "Dosya okumak", "Thread oluşturmak", "UI çizmek"],
                        0,
                        "Stream map/filter/reduce benzeri akıştır.",
                    ),
                    _mcq(
                        "medium",
                        "Aşağıdakilerden hangisi intermediate operation örneğidir?",
                        ["map/filter", "collect", "forEach", "count"],
                        0,
                        "map/filter intermediate; collect/count terminal'dir (genel olarak).",
                    ),
                    _tf(
                        "hard",
                        "Stream'ler genelde lazy çalışır; terminal operation gelince değerlendirilir.",
                        True,
                        "Pipeline terminal op ile çalışır.",
                    ),
                ]

        # --- C (deep topics) ---
        if lid == "c":
            if tid in ("c-pointer-bellek",):
                b += [
                    _mcq(
                        "easy",
                        "C'de pointer değişkeni hangi operatörle dereference edilir?",
                        ["*", "&", "->", "."],
                        0,
                        "*p adresin gösterdiği değeri verir.",
                    ),
                    _mcq(
                        "medium",
                        "`&x` ifadesi ne üretir?",
                        ["x'in adresi", "x'in değeri", "x'in tipi", "x'in uzunluğu"],
                        0,
                        "& adres operatörüdür.",
                    ),
                    _tf(
                        "hard",
                        "Stack'te tanımlanan bir değişkenin adresini return edip kullanmak dangling pointer riskidir.",
                        True,
                        "Fonksiyon bitince stack alanı geçersizleşir.",
                    ),
                ]
            if tid in ("c-array-string",):
                b += [
                    _mcq(
                        "easy",
                        "C'de string genelde nasıl temsil edilir?",
                        ["\\0 ile biten char dizisi", "Unicode obje", "immutable string", "hash map"],
                        0,
                        "C string null-terminated char array'dir.",
                    ),
                    _mcq(
                        "medium",
                        "`strlen(\"abc\")` sonucu nedir?",
                        ["3", "4", "0", "2"],
                        0,
                        "Null karakter sayılmaz.",
                    ),
                    _tf(
                        "hard",
                        "C'de `sizeof(arr)` ile `sizeof(ptr)` aynı şey değildir; arr pointer'a decay edebilir.",
                        True,
                        "Bağlama göre farklıdır.",
                    ),
                ]

        # --- SQL deep ---
        if lid == "sql":
            if tid in ("sql-joins",):
                b += [
                    _mcq(
                        "easy",
                        "INNER JOIN ne yapar?",
                        ["Eşleşen satırları getirir", "Tüm satırları getirir", "Sadece soldakileri getirir", "Sadece sağdakileri getirir"],
                        0,
                        "Eşleşen kayıtlar gelir.",
                    ),
                    _mcq(
                        "medium",
                        "LEFT JOIN'de sağ tabloda eşleşme yoksa sağ taraf kolonları genelde ne olur?",
                        ["NULL", "0", "boş string", "hata verir"],
                        0,
                        "Eşleşmeyen tarafta NULL olur.",
                    ),
                    _tf(
                        "hard",
                        "JOIN koşulunu yanlış yazmak kartesyen çarpıma (çok fazla satır) sebep olabilir.",
                        True,
                        "Yanlış koşul satırları katlar.",
                    ),
                ]
            if tid in ("sql-index",):
                b += [
                    _mcq(
                        "easy",
                        "Index'in en tipik faydası nedir?",
                        ["Okuma sorgularını hızlandırmak", "Her şeyi küçültmek", "Her zaman yazmayı hızlandırmak", "NULL'u kaldırmak"],
                        0,
                        "Index okuma performansına yardım eder.",
                    ),
                    _tf(
                        "medium",
                        "Çok fazla index, insert/update maliyetini artırabilir.",
                        True,
                        "Her yazmada index güncellenir.",
                    ),
                    _mcq(
                        "hard",
                        "Index performansını anlamak için tipik hangi araç/komut kullanılır?",
                        ["EXPLAIN", "PRINT", "SHOW UI", "COMPILE"],
                        0,
                        "EXPLAIN plan gösterir.",
                    ),
                ]

        # --- DART deep ---
        if lid == "dart":
            if tid in ("dart-degiskenler", "dart-giris"):
                b += [
                    _mcq(
                        "easy",
                        "Dart'ta `var` ile `final` arasındaki temel fark hangisidir?",
                        ["final tek atamadır; var yeniden atanabilir", "var sadece int olur", "final sadece class içinde olur", "ikisi aynıdır"],
                        0,
                        "final bir kez atanır; var yeniden atanabilir.",
                    ),
                    _mcq(
                        "medium",
                        "Dart'ta `late` ne zaman kullanılır?",
                        ["Sonradan atanacak ama nullable yapmak istemediğinde", "Her zaman null için", "Sadece listeler için", "Sadece async için"],
                        0,
                        "late, gecikmeli başlatma içindir.",
                    ),
                    _tf(
                        "hard",
                        "Dart null-safety ile `String` ve `String?` aynı değildir; `String?` null olabilir.",
                        True,
                        "Nullable tipler `?` ile gösterilir.",
                    ),
                ]
            if tid in ("dart-kontrol-akisi",):
                b += [
                    _mcq(
                        "easy",
                        "Dart'ta koşul ifadesi için hangisi doğrudur?",
                        ["if (...) { ... }", "if ... then ...", "IF (...) BEGIN", "cond { ... }"],
                        0,
                        "Dart C-benzeri blok yapısı kullanır.",
                    ),
                    _mcq(
                        "medium",
                        "Bu döngü kaç kez çalışır?\n\nfor (var i=0; i<3; i++) { }",
                        ["3", "2", "4", "0"],
                        0,
                        "i=0,1,2 → 3 kez.",
                    ),
                    _tf(
                        "hard",
                        "Dart'ta `switch` içinde `break` kullanımı önemlidir (sürüm/kalıba göre).",
                        True,
                        "Switch fallthrough davranışı/kuralları sürüme göre değişebilir; dikkat gerekir.",
                    ),
                ]
            if tid in ("dart-collections",):
                b += [
                    _mcq(
                        "easy",
                        "Dart'ta liste literal'i hangisidir?",
                        ["[1,2,3]", "{1,2,3}", "(1,2,3)", "<1,2,3>"],
                        0,
                        "Liste [] ile yazılır.",
                    ),
                    _mcq(
                        "medium",
                        "Map literal'i hangisidir?",
                        ["{'a': 1}", "['a': 1]", "{'a', 1}", "(a:1)"],
                        0,
                        "Map süslü parantez + key:value ile yazılır.",
                    ),
                    _tf(
                        "hard",
                        "Bir `Set`, aynı değeri iki kez eklemeye çalışırsan benzersiz tuttuğu için tekrarı engeller.",
                        True,
                        "Set unique tutar.",
                    ),
                ]
            if tid in ("dart-async",):
                b += [
                    _mcq(
                        "easy",
                        "Dart'ta async fonksiyonlar genelde ne döndürür?",
                        ["Future", "Promise", "Thread", "Task"],
                        0,
                        "Dart async işleri Future ile temsil eder.",
                    ),
                    _mcq(
                        "medium",
                        "`await` ne yapar?",
                        ["Future tamamlanana kadar bekler", "Thread açar", "GC çalıştırır", "Tip kontrolü yapar"],
                        0,
                        "await Future sonucunu bekler.",
                    ),
                    _tf(
                        "hard",
                        "`Future.wait([...])` bağımsız Future'ları beraber beklemek için kullanılır.",
                        True,
                        "Paralel bekleme yapar.",
                    ),
                ]
            if tid in ("dart-oop",):
                b += [
                    _mcq(
                        "easy",
                        "Dart'ta interface gibi davranan şey en çok hangisidir?",
                        ["abstract class / implements", "package", "mixin zorunlu", "namespace"],
                        0,
                        "implements ile interface benzeri kullanım olur.",
                    ),
                    _tf(
                        "medium",
                        "Dart'ta `extends` kalıtım, `implements` arayüz sözleşmesi içindir.",
                        True,
                        "İkisi farklı amaçlara hizmet eder.",
                    ),
                    _mcq(
                        "hard",
                        "Factory constructor için doğru ifade hangisidir?",
                        ["Her zaman yeni instance dönmek zorunda değildir", "Sadece int döndürür", "Sadece async çalışır", "Sadece private olur"],
                        0,
                        "factory farklı instance döndürebilir (cache vb.).",
                    ),
                ]
            if tid in ("dart-test",):
                b += [
                    _mcq(
                        "easy",
                        "Testin temel amacı nedir?",
                        ["Davranışı doğrulamak ve regresyonu yakalamak", "Kodu hızlandırmak", "UI çizmek", "Derleyiciyi değiştirmek"],
                        0,
                        "Testler doğrulama ve güvence sağlar.",
                    ),
                    _tf(
                        "medium",
                        "Birim testler genelde küçük bir fonksiyon/sınıf davranışını izole test eder.",
                        True,
                        "Unit test izolasyon hedefler.",
                    ),
                    _mcq(
                        "hard",
                        "Mock/stub kullanmanın temel amacı hangisidir?",
                        ["Dış bağımlılıkları izole etmek", "Kodu derlemek", "Tipleri silmek", "Sadece UI test etmek"],
                        0,
                        "Bağımlılıkları taklit eder.",
                    ),
                ]

        # --- TYPESCRIPT deep ---
        if lid == "typescript":
            if tid in ("ts-tip-sistemi", "ts-union"):
                b += [
                    _mcq(
                        "easy",
                        "TypeScript'te union type örneği hangisidir?",
                        ["string | number", "string & number", "string -> number", "string || number"],
                        0,
                        "Union `|` ile yazılır.",
                    ),
                    _mcq(
                        "medium",
                        "TypeScript'te type narrowing genelde ne ile yapılır?",
                        ["typeof/instanceof/guard", "console.log", "import", "await"],
                        0,
                        "Narrowing kontrol ifadeleriyle yapılır.",
                    ),
                    _tf(
                        "hard",
                        "`never` tipi, gerçekleşmesi mümkün olmayan durumları ifade etmek için kullanılır.",
                        True,
                        "Exhaustive check vb. için kullanılır.",
                    ),
                ]
            if tid in ("ts-generics",):
                b += [
                    _mcq(
                        "easy",
                        "Generic tanımlamada en sık hangi sembol kullanılır?",
                        ["<T>", "{T}", "(T)", "[T]"],
                        0,
                        "Generic parametreleri <T> şeklindedir.",
                    ),
                    _mcq(
                        "medium",
                        "Generic'in temel faydası nedir?",
                        ["Tip güvenli tekrar kullanılabilirlik", "Runtime hızlandırma", "Belleği sıfırlama", "JS'i değiştirme"],
                        0,
                        "Aynı fonksiyon/sınıfı farklı tiplerle güvenli kullanırsın.",
                    ),
                    _tf(
                        "hard",
                        "TypeScript generics genelde runtime'da yoktur; derleme zamanı tip bilgisidir.",
                        True,
                        "TS tipleri compile-time içindir.",
                    ),
                ]

        # --- CPP deep ---
        if lid == "cpp":
            if tid in ("cpp-oop",):
                b += [
                    _mcq(
                        "easy",
                        "C++'ta destructor ne zaman çağrılır?",
                        ["Nesne scope'tan çıkınca / delete edilince", "Her satır sonunda", "Sadece main'de", "Sadece malloc sonrası"],
                        0,
                        "RAII ile kaynaklar otomatik bırakılır.",
                    ),
                    _tf(
                        "medium",
                        "C++'ta virtual fonksiyonlar polymorphism için kullanılır.",
                        True,
                        "Dinamik dispatch sağlar.",
                    ),
                    _mcq(
                        "hard",
                        "RAII'nin temel fikri hangisidir?",
                        ["Kaynak yönetimini nesne ömrüne bağlamak", "Her şeyi global yapmak", "Her şeyi pointer yapmak", "GC zorunlu"],
                        0,
                        "Kaynaklar constructor'da alınır, destructor'da bırakılır.",
                    ),
                ]
            if tid in ("cpp-stl",):
                b += [
                    _mcq(
                        "easy",
                        "C++'ta dinamik diziye en yakın STL yapısı hangisidir?",
                        ["std::vector", "std::map", "std::set", "std::string_view"],
                        0,
                        "Vector dinamik dizi gibidir.",
                    ),
                    _mcq(
                        "medium",
                        "std::map anahtarları nasıl saklar?",
                        ["Sıralı (tree)", "Rastgele", "Sadece insertion order", "Sadece hash ile"],
                        0,
                        "std::map tipik olarak tree tabanlıdır.",
                    ),
                    _tf(
                        "hard",
                        "Iterator invalidation, bazı container'larda ekleme/silme sonrası iterator'ların bozulmasıdır.",
                        True,
                        "Özellikle vector'da reallocation ile olur.",
                    ),
                ]

        # --- GO deep ---
        if lid == "go":
            if tid in ("go-error",):
                b += [
                    _mcq(
                        "easy",
                        "Go'da hata dönüşü için en yaygın yaklaşım hangisidir?",
                        ["(value, error) döndürmek", "throw/catch", "panic her yerde", "null error yoktur"],
                        0,
                        "Go explicit error döndürür.",
                    ),
                    _tf(
                        "medium",
                        "Go'da `error` bir interface'tir.",
                        True,
                        "error interface { Error() string }",
                    ),
                    _mcq(
                        "hard",
                        "Go'da `defer` için doğru ifade hangisidir?",
                        ["Fonksiyon çıkışında çalışır", "Derleme zamanında çalışır", "Sadece loop'ta çalışır", "Sadece goroutine'de çalışır"],
                        0,
                        "Defer cleanup için kullanılır.",
                    ),
                ]
            if tid in ("go-concurrency",):
                b += [
                    _mcq(
                        "easy",
                        "Go'da hafif eşzamanlılık birimi hangisidir?",
                        ["goroutine", "thread", "process", "fiber (zorunlu)"],
                        0,
                        "Go goroutine kullanır.",
                    ),
                    _mcq(
                        "medium",
                        "Channel ne için kullanılır?",
                        ["Goroutine'ler arası iletişim", "Dosya açma", "UI çizme", "Tip kontrolü"],
                        0,
                        "Channel mesajlaşma sağlar.",
                    ),
                    _tf(
                        "hard",
                        "Race condition, aynı veriye eşzamanlı erişimde yanlış sonuç üretebilir.",
                        True,
                        "Senkronizasyon gerekir.",
                    ),
                ]

        # --- RUST deep ---
        if lid == "rust":
            if tid in ("rust-temeller", "rust-giris"):
                b += [
                    _mcq(
                        "easy",
                        "Rust'ta değişkenler varsayılan olarak nasıldır?",
                        ["immutable", "mutable", "null", "dynamic"],
                        0,
                        "mut yazmazsan immutable'dır.",
                    ),
                    _mcq(
                        "medium",
                        "Rust'ta ownership'in temel amacı nedir?",
                        ["Bellek güvenliği (GC olmadan)", "UI çizimi", "SQL çalıştırma", "Thread saymak"],
                        0,
                        "Ownership bellek güvenliği sağlar.",
                    ),
                    _tf(
                        "hard",
                        "Borrow checker, derleme zamanında veri yarışlarını ve dangling reference'ı engellemeyi hedefler.",
                        True,
                        "Compile-time güvenlik sağlar.",
                    ),
                ]
            if tid in ("rust-traits",):
                b += [
                    _mcq(
                        "easy",
                        "Trait en çok neye benzer?",
                        ["Interface", "Package manager", "Thread", "Garbage collector"],
                        0,
                        "Trait davranış sözleşmesidir.",
                    ),
                    _tf(
                        "medium",
                        "Rust'ta generics + trait bound ile tip kısıtı konulabilir.",
                        True,
                        "T: SomeTrait gibi.",
                    ),
                    _mcq(
                        "hard",
                        "`impl Trait` kullanımı neyi kolaylaştırır?",
                        ["Dönüş tipini soyutlamayı", "Pointer aritmetiğini", "GC'yi", "SQL join'i"],
                        0,
                        "Dönüş tipi karmaşasını azaltır.",
                    ),
                ]
            if tid in ("rust-lifetime",):
                b += [
                    _mcq(
                        "easy",
                        "Lifetime anotasyonlarının temel amacı nedir?",
                        ["Referansların ne kadar yaşayacağını belirtmek", "Thread açmak", "UI çizmek", "Dosya yazmak"],
                        0,
                        "Borrow ilişkisini ifade eder.",
                    ),
                    _tf(
                        "hard",
                        "Yanlış lifetime tasarımı derleme hatası üretir; runtime crash yerine compile-time hata hedeflenir.",
                        True,
                        "Rust felsefesi budur.",
                    ),
                ]

        # --- SWIFT deep ---
        if lid == "swift":
            if tid in ("swift-struct-class",):
                b += [
                    _mcq(
                        "easy",
                        "Swift'te struct ve class için en temel fark hangisidir?",
                        ["struct value type, class reference type", "struct sadece private", "class sadece int", "ikisi aynıdır"],
                        0,
                        "Value vs reference farkı önemlidir.",
                    ),
                    _tf(
                        "medium",
                        "Swift'te struct kopyalanınca değer kopyalanır (value semantics).",
                        True,
                        "Genelde value semantics.",
                    ),
                    _mcq(
                        "hard",
                        "ARC neyi yönetir?",
                        ["Reference counting ile memory", "SQL index", "UI layout", "Thread scheduling"],
                        0,
                        "ARC bellek yönetir.",
                    ),
                ]
            if tid in ("swift-async",):
                b += [
                    _mcq(
                        "easy",
                        "Swift concurrency'de async/await neyi kolaylaştırır?",
                        ["Asenkron kodu okunur yazmayı", "Pointer aritmetiğini", "SQL join'i", "Derleyiciyi kapatmayı"],
                        0,
                        "Okunabilir async sağlar.",
                    ),
                    _tf(
                        "hard",
                        "Structured concurrency, görevlerin ömrünü hiyerarşiyle yönetmeyi hedefler.",
                        True,
                        "Task lifecycle düzenler.",
                    ),
                ]

        # --- KOTLIN deep ---
        if lid == "kotlin":
            if tid in ("kotlin-coroutines",):
                b += [
                    _mcq(
                        "easy",
                        "Kotlin'de coroutine için en doğru ifade hangisidir?",
                        ["Hafif asenkron iş birimi", "Zorunlu thread", "Sadece UI", "Sadece SQL"],
                        0,
                        "Coroutine hafif iş birimidir.",
                    ),
                    _mcq(
                        "medium",
                        "suspend fonksiyon neyi ifade eder?",
                        ["Askıya alınabilir/asenkron", "Her zaman blocking", "Sadece test", "Sadece class"],
                        0,
                        "Suspend bekleyebilir.",
                    ),
                    _tf(
                        "hard",
                        "Coroutine scope iptal edilirse child işler de iptal olabilir (structured concurrency).",
                        True,
                        "Scope hiyerarşisi.",
                    ),
                ]
            if tid in ("kotlin-collections",):
                b += [
                    _mcq(
                        "easy",
                        "Kotlin'de immutable list oluşturmak için yaygın fonksiyon hangisidir?",
                        ["listOf", "new List()", "Array()", "mklist"],
                        0,
                        "listOf immutable list döndürebilir.",
                    ),
                    _mcq(
                        "medium",
                        "map/filter hangi tip işlemdir?",
                        ["koleksiyon dönüşümü", "dosya okuma", "thread yönetimi", "ui çizimi"],
                        0,
                        "Fonksiyonel dönüşüm.",
                    ),
                ]

        # --- PHP deep ---
        if lid == "php":
            if tid in ("php-web",):
                b += [
                    _mcq(
                        "easy",
                        "PHP en çok hangi ortamda kullanılır?",
                        ["Web backend", "GPU shader", "Kernel driver", "Firmware zorunlu"],
                        0,
                        "PHP web backend'de yaygındır.",
                    ),
                    _tf(
                        "medium",
                        "PHP'de superglobal örneği: $_GET, $_POST",
                        True,
                        "HTTP parametreleri için kullanılır.",
                    ),
                    _mcq(
                        "hard",
                        "XSS'e karşı temel savunma hangisidir?",
                        ["Output escaping", "Her şeyi base64", "SQL index", "Thread lock"],
                        0,
                        "Çıktıyı escape etmek gerekir.",
                    ),
                ]
            if tid in ("php-guvenlik",):
                b += [
                    _mcq(
                        "easy",
                        "SQL injection'a karşı en doğru yaklaşım hangisidir?",
                        ["Prepared statements", "String birleştirme", "Sadece regex", "Hiç kontrol etmemek"],
                        0,
                        "Prepared statement güvenlidir.",
                    ),
                    _tf(
                        "hard",
                        "Kullanıcı girdisini doğrudan HTML'e basmak XSS riski yaratır.",
                        True,
                        "Escape/sanitize gerekir.",
                    ),
                ]

        # --- RUBY deep ---
        if lid == "ruby":
            if tid in ("ruby-oop",):
                b += [
                    _mcq(
                        "easy",
                        "Ruby'de instance değişkeni nasıl yazılır?",
                        ["@name", "$name", "%name", "&name"],
                        0,
                        "@ instance variable'dır.",
                    ),
                    _tf(
                        "medium",
                        "Ruby'de her şey objedir (pratikte).",
                        True,
                        "Ruby object model.",
                    ),
                ]
            if tid in ("ruby-gem",):
                b += [
                    _mcq(
                        "easy",
                        "Ruby'de bağımlılık yönetimi için yaygın araç hangisidir?",
                        ["Bundler", "npm", "pip", "maven"],
                        0,
                        "Bundler Gemfile kullanır.",
                    ),
                    _tf(
                        "hard",
                        "Gemfile.lock, bağımlılık sürümlerini sabitlemeye yardımcı olur.",
                        True,
                        "Reproducible build sağlar.",
                    ),
                ]

        # --- R deep ---
        if lid == "r":
            if tid in ("r-plot",):
                b += [
                    _mcq(
                        "easy",
                        "R'de vektör oluşturmak için yaygın fonksiyon hangisidir?",
                        ["c(1,2,3)", "vec(1,2,3)", "[1,2,3]", "{1,2,3}"],
                        0,
                        "c() combine eder.",
                    ),
                    _tf(
                        "medium",
                        "R'de data frame tablo benzeri veri yapısıdır.",
                        True,
                        "Tabular veri için kullanılır.",
                    ),
                ]
            if tid in ("r-paket",):
                b += [
                    _mcq(
                        "easy",
                        "R'de paket kurmak için yaygın fonksiyon hangisidir?",
                        ["install.packages()", "pip install", "npm i", "brew install"],
                        0,
                        "install.packages() kullanılır.",
                    ),
                    _tf(
                        "hard",
                        "library(pkg) paketi yükler; install.packages() kurar.",
                        True,
                        "İkisi farklıdır.",
                    ),
                ]

        # --- MATLAB (Octave) deep ---
        if lid == "matlab":
            if tid in ("matlab-matris",):
                b += [
                    _mcq(
                        "easy",
                        "MATLAB'da matris oluşturmak için köşeli parantez nasıl kullanılır?",
                        ["[1 2; 3 4]", "(1 2; 3 4)", "{1,2;3,4}", "<1 2; 3 4>"],
                        0,
                        "[] ile satır/kolon yazılır.",
                    ),
                    _mcq(
                        "medium",
                        "MATLAB'da eleman bazlı çarpma için hangi operatör kullanılır?",
                        [".*", "*", "x", "mul"],
                        0,
                        ".* element-wise çarpmadır.",
                    ),
                    _tf(
                        "hard",
                        "MATLAB'da 1-indexing vardır (ilk eleman index 1).",
                        True,
                        "MATLAB 1-indexed'dir.",
                    ),
                ]
            if tid in ("matlab-plot",):
                b += [
                    _mcq(
                        "easy",
                        "MATLAB'da basit çizim için en yaygın fonksiyon hangisidir?",
                        ["plot", "draw", "chartit", "render"],
                        0,
                        "plot temel çizim fonksiyonudur.",
                    ),
                    _tf(
                        "medium",
                        "figure() yeni bir grafik penceresi açabilir.",
                        True,
                        "Yeni figure oluşturur.",
                    ),
                ]

        # --- Curriculum-wide deep generator (all languages / all topics) ---
        # The explicit per-topic blocks above cover many hotspots, but we also want
        # every topic id to get rich, non-generic questions.
        CURRICULUM_CATEGORY: dict[str, dict[str, str]] = {
            "python": {
                "py-kurulum": "intro",
                "py-degiskenler": "types",
                "py-kosul-dongu": "control",
                "py-fonksiyonlar": "functions",
                "py-koleksiyonlar": "collections",
                "py-string": "string",
                "py-dosya": "files",
                "py-hatalar": "errors",
                "py-oop": "oop",
                "py-ileri": "advanced",
            },
            "javascript": {
                "js-giris": "intro",
                "js-tipler": "types",
                "js-kontrol": "control",
                "js-fonksiyon": "functions",
                "js-obj-array": "collections",
                "js-dom": "advanced",
                "js-async": "async",
                "js-moduller": "advanced",
                "js-test": "testing",
                "js-proje": "advanced",
                "js-syntax": "types",
                "js-fonksiyonlar": "functions",
                "js-array-obj": "collections",
                "js-uzmanliga-gecis": "advanced",
            },
            "typescript": {
                "ts-giris": "intro",
                "ts-tip-sistemi": "types",
                "ts-union": "types",
                "ts-generics": "advanced",
                "ts-moduller": "advanced",
                "ts-uzmanliga-gecis": "advanced",
            },
            "dart": {
                "dart-giris": "intro",
                "dart-degiskenler": "types",
                "dart-kontrol-akisi": "control",
                "dart-fonksiyonlar": "functions",
                "dart-collections": "collections",
                "dart-async": "async",
                "dart-oop": "oop",
                "dart-test": "testing",
            },
            "c": {
                "c-giris": "intro",
                "c-degiskenler": "types",
                "c-operatorler": "types",
                "c-kontrol-akisi": "control",
                "c-fonksiyonlar": "functions",
                "c-array-string": "string",
                "c-pointer-bellek": "memory",
                "c-struct": "oop",
                "c-dosya": "files",
                "c-debug-perf": "advanced",
            },
            "cpp": {
                "cpp-baslangic": "intro",
                "cpp-io-ve-turler": "types",
                "cpp-oop": "oop",
                "cpp-memory": "memory",
                "cpp-stl": "collections",
                "cpp-ileri": "advanced",
            },
            "java": {
                "java-giris": "intro",
                "java-degiskenler": "types",
                "java-kontrol-akisi": "control",
                "java-oop": "oop",
                "java-collections": "collections",
                "java-streams": "advanced",
                "java-exceptions": "errors",
                "java-concurrency": "async",
                "java-test": "testing",
            },
            "swift": {
                "swift-giris": "intro",
                "swift-temeller": "types",
                "swift-kontrol-akisi": "control",
                "swift-fonksiyon": "functions",
                "swift-struct-class": "oop",
                "swift-protokoller": "oop",
                "swift-async": "async",
                "swift-test": "testing",
            },
            "kotlin": {
                "kotlin-giris": "intro",
                "kotlin-temeller": "types",
                "kotlin-fonksiyon": "functions",
                "kotlin-collections": "collections",
                "kotlin-oop": "oop",
                "kotlin-coroutines": "async",
                "kotlin-test": "testing",
            },
            "php": {
                "php-giris": "intro",
                "php-syntax": "types",
                "php-fonksiyon": "functions",
                "php-oop": "oop",
                "php-web": "advanced",
                "php-guvenlik": "advanced",
                "php-composer": "advanced",
            },
            "ruby": {
                "ruby-giris": "intro",
                "ruby-temeller": "types",
                "ruby-fonksiyon": "functions",
                "ruby-oop": "oop",
                "ruby-gem": "advanced",
                "ruby-test": "testing",
            },
            "go": {
                "go-giris": "intro",
                "go-temeller": "types",
                "go-struct": "oop",
                "go-error": "errors",
                "go-concurrency": "async",
                "go-test": "testing",
            },
            "rust": {
                "rust-giris": "intro",
                "rust-temeller": "types",
                "rust-collections": "collections",
                "rust-traits": "oop",
                "rust-lifetime": "memory",
                "rust-async": "async",
                "rust-test": "testing",
            },
            "r": {
                "r-giris": "intro",
                "r-temeller": "types",
                "r-plot": "advanced",
                "r-istatistik": "advanced",
                "r-paket": "advanced",
            },
            "matlab": {
                "matlab-giris": "intro",
                "matlab-matris": "types",
                "matlab-fonksiyon": "functions",
                "matlab-plot": "advanced",
                "matlab-toolbox": "advanced",
            },
            "sql": {
                "sql-giris": "intro",
                "sql-temeller": "types",
                "sql-joins": "sql",
                "sql-group": "sql",
                "sql-index": "sql",
                "sql-transactions": "sql",
                "sql-window": "sql",
            },
        }

        def curriculum_category(language_id: str, topic_id2: str) -> str | None:
            return (CURRICULUM_CATEGORY.get((language_id or "").lower()) or {}).get(
                (topic_id2 or "").lower()
            )

        def deep_for_curriculum_topic() -> list[tuple]:
            # Map each curriculum topic-id to a coarse category.
            # (Keeps the generator deterministic and scalable.)
            cat = curriculum_category(lid, tid)
            if not cat:
                return []

            # Helpers to inject language flavor into answers.
            comment = a.get("comment", "//")
            null_word = a.get("null", "null")
            func_word = a.get("func", "function")

            out: list[tuple] = []

            # Category question sets (topic-specific by construction).
            if cat == "intro":
                out += [
                    _mcq("easy", f"[{ln} • {tt}] Yorum satırı genelde hangi biçimle başlar?", [comment, "#", "--", "/* */"], 0, f"{ln} için en yaygın yorum başlatıcısı: {comment}"),
                    _mcq("easy", f"[{ln} • {tt}] 'Boş değer' kavramına en yakın ifade hangisidir?", [null_word, "zero", "empty", "undefined"], 0, "Dillerde boş değer temsili farklıdır."),
                    _mcq("medium", f"[{ln} • {tt}] Fonksiyon tanımlamaya en yakın anahtar kelime hangisidir?", [func_word, "class", "package", "import"], 0, "Dil kimliğini yansıtır."),
                    _tf("hard", f"[{ln} • {tt}] Hata mesajında ilk hatayı çözmek, sonraki hataları da azaltabilir.", True, "Hata zinciri yaygındır."),
                ]
            elif cat == "types":
                out += [
                    _mcq(
                        "easy",
                        f"[{ln} • {tt}] Boolean değerleri en çok hangisine benzer?",
                        [f"{a['bool_true']}/{a['bool_false']}", "yes/no", "1/2", "ok/fail"],
                        0,
                        "Boolean true/false karşılıkları dile göre değişir.",
                    ),
                    _mcq("easy", f"[{ln} • {tt}] {null_word} kontrolü neden önemlidir?", ["Null reference hatalarını önlemek", "UI çizmek", "Index oluşturmak", "Derleyiciyi hızlandırmak"], 0, "Null dereference yaygın hatadır."),
                    _mcq("medium", f"[{ln} • {tt}] Tip dönüşümünde en kritik risk hangisidir?", ["Veri kaybı", "UI rengi", "Dosya adı", "Yorum uzunluğu"], 0, "Örn: ondalık→int veri kaybı."),
                    _tf("hard", f"[{ln} • {tt}] Otomatik tip dönüşümleri bazı dillerde sürpriz sonuç üretebilir.", True, "Örn: '5'+2 gibi."),
                ]
            elif cat == "control":
                out += [
                    _mcq("easy", f"[{ln} • {tt}] Koşulların temel amacı nedir?", ["Karar vermek", "Sadece yazdırmak", "Belleği silmek", "Paket yüklemek"], 0, "Kontrol akışı karar verir."),
                    _mcq("easy", f"[{ln} • {tt}] Döngülerin temel amacı nedir?", ["Tekrarlı işleri yapmak", "Adres almak", "Class oluşturmak", "Import yapmak"], 0, "Tekrar için."),
                    _mcq("medium", f"[{ln} • {tt}] Off-by-one hatası genelde hangi durumda olur?", ["Sınırları yanlış kurunca", "Değişken adı uzun olunca", "Yorum satırı ekleyince", "Dosya ismi kısa olunca"], 0, "Sınır değerler kritiktir."),
                    _tf("hard", f"[{ln} • {tt}] Sonsuz döngü genelde koşul/indeks hiç değişmediğinde oluşur.", True, "Koşul değişmiyorsa döngü durmaz."),
                ]
            elif cat == "functions":
                out += [
                    _mcq("easy", f"[{ln} • {tt}] Fonksiyonların temel faydası nedir?", ["Tekrarı azaltmak", "Her zaman hızlandırmak", "Belleği artırmak", "Hata üretmek"], 0, "Kodu düzenler."),
                    _fill("easy", f"[{ln} • {tt}] Fonksiyon anahtar kelimesi/kalıbı: ______", func_word, "Dil ailesine göre değişir."),
                    _mcq("medium", f"[{ln} • {tt}] Return (dönüş) ifadesinin amacı nedir?", ["Sonuç döndürmek", "Yorum eklemek", "Dosya silmek", "Index oluşturmak"], 0, "Fonksiyon sonucu."),
                    _tf("hard", f"[{ln} • {tt}] Parametreler ve dönüş değeri, fonksiyon sözleşmesinin parçasıdır.", True, "İmza önemlidir."),
                ]
            elif cat == "collections":
                out += [
                    _mcq("easy", f"[{ln} • {tt}] Benzersiz eleman tutmak için hangisi uygundur?", ["Set", "List/Array", "String", "Number"], 0, "Set unique tutar."),
                    _mcq("easy", f"[{ln} • {tt}] Anahtar→değer erişimi için hangisi uygundur?", ["Map/Dict", "List/Array", "Stack", "Queue"], 0, "Key-value yapısı."),
                    _tf("easy", f"[{ln} • {tt}] Liste/array sıralı veri tutar.", True, "Index ile erişim."),
                    _mcq("medium", f"[{ln} • {tt}] Filtreleme işlemi ne yapar?", ["Şarta uyanları seçer", "Tümünü ters çevirir", "Hepsini siler", "Hepsini kopyalar"], 0, "Predicate ile seçer."),
                ]
            elif cat == "string":
                out += [
                    _mcq("easy", f"[{ln} • {tt}] String'in uzunluğunu bulmak genelde neyi verir?", ["Karakter sayısı", "Kelime sayısı", "Dosya boyutu", "RAM miktarı"], 0, "Length/len."),
                    _tf("easy", f"[{ln} • {tt}] String birleştirme (concat) birçok dilde vardır.", True, "+ veya method."),
                    _mcq("medium", f"[{ln} • {tt}] Trim ne yapar?", ["Baş/son boşlukları kaldırır", "Sayıları toplar", "Listeyi sıralar", "Pointer üretir"], 0, "Whitespace temizler."),
                    _mcq("hard", f"[{ln} • {tt}] Substring/slice ne işe yarar?", ["Parça almak", "Dosya açmak", "Thread açmak", "Index yaratmak"], 0, "Parça."),
                ]
            elif cat == "files":
                out += [
                    _mcq("easy", f"[{ln} • {tt}] Dosya okuma/yazmada en kritik adım hangisidir?", ["Dosyayı kapatmak", "UI çizmek", "Index oluşturmak", "Thread öldürmek"], 0, "Kaynak yönetimi."),
                    _tf("easy", f"[{ln} • {tt}] Dosya yolu hatalıysa okuma işlemi hata verebilir.", True, "File not found."),
                    _mcq("medium", f"[{ln} • {tt}] Text dosyalarında encoding neden önemlidir?", ["Türkçe karakterler bozulmasın diye", "Sadece hız için", "Sadece renk için", "Sadece güvenlik için"], 0, "UTF-8 vb."),
                    _mcq("hard", f"[{ln} • {tt}] Append modu ne yapar?", ["Sona ekler", "Dosyayı siler", "Sadece okur", "Belleği sıfırlar"], 0, "Overwrite etmez."),
                ]
            elif cat == "errors":
                out += [
                    _mcq("easy", f"[{ln} • {tt}] Exception/hata yönetiminin amacı nedir?", ["Hataları kontrollü ele almak", "Hataları gizlemek", "UI çizmek", "Index oluşturmak"], 0, "Kontrol sağlar."),
                    _tf("easy", f"[{ln} • {tt}] Hata mesajındaki ilk satır genelde en kritik ipucunu verir.", True, "Özellikle ilk hata."),
                    _mcq("medium", f"[{ln} • {tt}] En iyi yaklaşım hangisidir?", ["Spesifik hatayı yakalamak", "Her şeyi yutmak", "Hiç yakalamamak", "Sadece print"], 0, "Spesifik daha iyidir."),
                    _mcq("hard", f"[{ln} • {tt}] Stack trace ne sağlar?", ["Hata zincirini/satırları", "UI düzenini", "Index listesini", "Paket sürümlerini"], 0, "Call stack bilgisi."),
                ]
            elif cat == "oop":
                out += [
                    _mcq("easy", f"[{ln} • {tt}] Encapsulation neyi hedefler?", ["Kontrollü erişim", "Her şeyi global", "Her şeyi public", "Hata üretmek"], 0, "API sınırı."),
                    _mcq("medium", f"[{ln} • {tt}] Inheritance/implements ne sağlar?", ["Davranış paylaşımı/sözleşme", "Dosya okuma", "Thread açma", "SQL join"], 0, "OOP kavramı."),
                    _tf("medium", f"[{ln} • {tt}] Interface/trait/protocol benzeri yapılar ortak sözleşme tanımlar.", True, "Dile göre adı değişir."),
                    _mcq("hard", f"[{ln} • {tt}] Constructor'ın amacı nedir?", ["Başlatmak", "Sıralamak", "Indexlemek", "Derlemek"], 0, "Init."),
                ]
            elif cat == "async":
                out += [
                    _mcq("easy", f"[{ln} • {tt}] Async'in temel amacı nedir?", ["Bloklamadan beklemeyi yönetmek", "Her şeyi hızlandırmak", "GC kapatmak", "Tipleri silmek"], 0, "IO beklemeleri."),
                    _tf("easy", f"[{ln} • {tt}] Bağımsız işler paralel yürütülebilir.", True, "Doğru olduğunda."),
                    _mcq("medium", f"[{ln} • {tt}] Race condition nedir?", ["Eşzamanlı erişim hatası", "Syntax hatası", "UI bug", "Index bug"], 0, "Concurrency hatası."),
                    _mcq("hard", f"[{ln} • {tt}] Deadlock nedir?", ["Karşılıklı kilitlenme", "Hız artışı", "Tip dönüşümü", "Dosya yok"], 0, "Kilitlenme."),
                ]
            elif cat == "testing":
                out += [
                    _mcq("easy", f"[{ln} • {tt}] Unit test neyi hedefler?", ["İzole davranışı", "Tüm sistemi", "Sadece UI", "Sadece DB"], 0, "Küçük birim."),
                    _mcq("easy", f"[{ln} • {tt}] Integration test neyi hedefler?", ["Bileşenlerin beraber çalışması", "Sadece değişken adı", "Sadece yorum", "Sadece index"], 0, "Entegrasyon."),
                    _tf("medium", f"[{ln} • {tt}] Testler regresyonu yakalamaya yardımcı olur.", True, "Değişiklik sonrası güvence."),
                    _mcq("hard", f"[{ln} • {tt}] Mock/stub neden kullanılır?", ["Bağımlılığı izole etmek", "Derleyiciyi değiştirmek", "UI boyamak", "Dosya silmek"], 0, "İzolasyon."),
                ]
            else:  # advanced
                out += [
                    _mcq(
                        "easy",
                        f"[{ln} • {tt}] Bu konu en çok hangi hedefe hizmet eder?",
                        [kw1, kw2, "UI tasarımı", "donanım tasarımı"],
                        0,
                        f"İçerik anahtar kelimelerine göre en ilgili hedef '{kw1}'.",
                    ),
                    _mcq(
                        "medium",
                        f"[{ln} • {tt}] Bu konu çalışılırken en sık hangi tür problemle karşılaşılır?",
                        ["hata ayıklama", "performans darboğazı", "derleme/build", "hepsi olabilir"],
                        3,
                        "İleri konularda debug/build/perf genelde birlikte düşünülür.",
                    ),
                    _tf(
                        "hard",
                        f"[{ln} • {tt}] Bu konudaki en önemli beceri, problemi küçük parçalara bölüp sistematik teşhis yapmaktır.",
                        True,
                        "İleri konular sistematik yaklaşım ister.",
                    ),
                    _mcq(
                        "hard",
                        f"[{ln} • {tt}] '{kw2}' ile ilgili doğru yaklaşım hangisidir?",
                        ["Önce ölç/kanıt, sonra değiştir", "Rastgele değiştir", "Hata mesajlarını yok say", "Testleri sil"],
                        0,
                        "Ölçüm/kanıt olmadan değişiklik yapmak zaman kaybettirir.",
                    ),
                ]

            # Remove generic strategy questions: they are not topic-specific and were a major complaint.

            return out

        b += deep_for_curriculum_topic()

        # --- Code-block-driven questions (highest specificity) ---
        # We extract fenced code blocks from the actual lesson markdown and generate
        # questions directly about them (output / missing token / meaning).
        @dataclass(frozen=True)
        class CodeBlock:
            lang: str
            code: str

        def extract_code_blocks(markdown: str) -> list[CodeBlock]:
            md2 = markdown or ""
            # ```lang\n...\n```
            blocks: list[CodeBlock] = []
            for m in re.finditer(r"```([a-zA-Z0-9_+-]*)\n([\s\S]*?)\n```", md2):
                lang = (m.group(1) or "").strip().lower()
                code = (m.group(2) or "").rstrip()
                if not code.strip():
                    continue
                blocks.append(CodeBlock(lang=lang, code=code))
            return blocks

        def _unescape_newlines(s: str) -> str:
            return s.replace("\\n", "\n").replace("\\t", "\t")

        def infer_output_literal(language_id: str, code: str) -> str | None:
            """
            Very conservative output inference:
            Only returns output for trivial single-print cases with a literal.
            """
            s = code.strip()
            lid2 = (language_id or "").lower()

            # Python: print("x") or print('x')
            if lid2 == "python":
                m = re.search(r"""^print\(\s*(['"])(.*?)\1\s*\)\s*$""", s, re.MULTILINE)
                if m:
                    return _unescape_newlines(m.group(2)) + "\n"

            # JS/TS: console.log("x");
            if lid2 in ("javascript", "typescript"):
                m = re.search(r"""^console\.log\(\s*(['"])(.*?)\1\s*\)\s*;?\s*$""", s, re.MULTILINE)
                if m:
                    return _unescape_newlines(m.group(2)) + "\n"

            # Dart: print("x");
            if lid2 == "dart":
                m = re.search(r"""^print\(\s*(['"])(.*?)\1\s*\)\s*;?\s*$""", s, re.MULTILINE)
                if m:
                    return _unescape_newlines(m.group(2)) + "\n"

            # C/C++: printf("x\n");
            if lid2 in ("c", "cpp"):
                m = re.search(r"""printf\(\s*(['"])(.*?)\1\s*\)\s*;""", s)
                if m:
                    return _unescape_newlines(m.group(2))

            # Java/Kotlin: System.out.println("x");
            if lid2 in ("java", "kotlin"):
                m = re.search(r"""System\.out\.println\(\s*(['"])(.*?)\1\s*\)\s*;""", s)
                if m:
                    return _unescape_newlines(m.group(2)) + "\n"

            # SQL: SELECT 5;
            if lid2 == "sql":
                m = re.search(r"""^\s*SELECT\s+([0-9]+)\s*;\s*$""", s, re.IGNORECASE | re.MULTILINE)
                if m:
                    return f"{m.group(1)}\n"

            return None

        def make_missing_token_question(language_id: str, cb: CodeBlock) -> tuple | None:
            lid2 = (language_id or "").lower()
            code = cb.code

            # Pick one very safe token to blank.
            if lid2 == "python":
                # blank a trailing ":" on def/if/for/while lines
                lines = code.splitlines()
                for i, line in enumerate(lines):
                    if re.match(r"^\s*(def|if|for|while)\b.*:\s*$", line):
                        new_line = re.sub(r":\s*$", "____", line)
                        shown = "\n".join(lines[:i] + [new_line] + lines[i + 1 :])
                        return _fill(
                            "medium",
                            f"[{ln} • {tt}] Aşağıdaki kodda eksik olan sembolü doldur.\n\n{shown}",
                            ":",
                            "Python'da def/if/for/while satırı ':' ile biter.",
                        )
                return None

            # C-style languages: missing ';' at end of a simple statement
            if lid2 in ("javascript", "typescript", "dart", "java", "kotlin", "swift", "php", "c", "cpp", "go", "rust"):
                lines = code.splitlines()
                for i, line in enumerate(lines):
                    l = line.rstrip()
                    if not l or l.strip().startswith(("//", "#", "--")):
                        continue
                    # safe candidates
                    if re.search(r"\b(print|printf|console\.log|System\.out\.println)\b", l) and l.endswith(";"):
                        new_line = l[:-1] + "____"
                        shown = "\n".join(lines[:i] + [new_line] + lines[i + 1 :])
                        return _fill(
                            "medium",
                            f"[{ln} • {tt}] Aşağıdaki kodda eksik olan sembolü doldur.\n\n{shown}",
                            ";",
                            "Bu dil ailesinde çoğu ifade ';' ile biter.",
                        )
                return None

            return None

        def make_code_questions_for_topic() -> list[tuple]:
            blocks = extract_code_blocks(md or "")

            # If the lesson has no (or too few) code blocks, we synthesize a couple of
            # tiny, topic-specific snippets using topic keywords. This guarantees that
            # every topic gets truly topic-specific questions.
            if len(blocks) < 2:
                cat = curriculum_category(lid, tid) or "advanced"
                kx = kw1 or tt

                def add_synth(lang_tag: str, code: str):
                    nonlocal blocks
                    if code.strip():
                        blocks = blocks + [CodeBlock(lang=lang_tag, code=code.strip())]

                if lid == "python":
                    if cat == "control":
                        add_synth("python", f"for i in range(1, 4):\n    print('{tt}:' + str(i))")
                    elif cat == "functions":
                        add_synth("python", f"def f(x):\n    return x * 2\n\nprint(f(3))")
                    elif cat == "collections":
                        add_synth("python", "nums = [1,2,3]\nprint(len(nums))")
                    elif cat == "string":
                        add_synth("python", f"s = '{kx}'\nprint(len(s))")
                    elif cat == "errors":
                        add_synth("python", "try:\n    print(1/0)\nexcept ZeroDivisionError:\n    print('err')")
                    else:
                        add_synth("python", f"print('{tt}')")
                elif lid in ("javascript", "typescript"):
                    if cat == "control":
                        add_synth("js", f"for (let i=1; i<=3; i++) console.log('{tt}:' + i);")
                    elif cat == "functions":
                        add_synth("js", "function f(x){ return x*2; }\nconsole.log(f(3));")
                    elif cat == "collections":
                        add_synth("js", "const nums = [1,2,3];\nconsole.log(nums.length);")
                    elif cat == "string":
                        add_synth("js", f"const s = '{kx}';\nconsole.log(s.length);")
                    elif cat == "async":
                        add_synth("js", "async function main(){ return 3; }\nmain().then(x=>console.log(x));")
                    else:
                        add_synth("js", f"console.log('{tt}');")
                elif lid == "dart":
                    if cat == "control":
                        add_synth("dart", f"void main() {{\n  for (var i=1; i<=3; i++) {{\n    print('{tt}:$i');\n  }}\n}}")
                    elif cat == "functions":
                        add_synth("dart", "int f(int x) => x * 2;\nvoid main(){ print(f(3)); }")
                    elif cat == "collections":
                        add_synth("dart", "void main(){ final nums=[1,2,3]; print(nums.length); }")
                    elif cat == "string":
                        add_synth("dart", f"void main(){{ final s='{kx}'; print(s.length); }}")
                    else:
                        add_synth("dart", f"void main() {{ print('{tt}'); }}")
                elif lid in ("c", "cpp"):
                    inc = "#include <stdio.h>\n"
                    if cat == "string":
                        add_synth("c", inc + f"int main(){{ printf(\"{tt}\\n\"); return 0; }}")
                    else:
                        add_synth("c", inc + "int main(){ printf(\"OK\\n\"); return 0; }")
                elif lid == "sql":
                    add_synth("sql", "SELECT 5;")
                else:
                    # Generic fallback: keep it safe and still topic-labeled
                    add_synth(lid, f"// {tt}\n")

            if not blocks:
                return []

            out: list[tuple] = []
            # Prefer blocks that match the language id; otherwise still use them as "reading" questions.
            # Cap so we don't drown the bank.
            used = 0
            for cb in blocks:
                if used >= 6:
                    break

                # Output question (easy) if we can infer safely.
                out_lit = infer_output_literal(lid, cb.code)
                if out_lit is not None:
                    out.append(
                        _mcq(
                            "easy",
                            f"[{ln} • {tt}] Bu kodun çıktısı nedir?\n\n{cb.code}",
                            [out_lit.rstrip("\n"), "(çıktı üretmez)", "Hata verir", "Bilinemez"],
                            0,
                            "Kodda doğrudan literal yazdırma var.",
                        )
                    )
                    used += 1

                # Missing token (medium)
                mt = make_missing_token_question(lid, cb)
                if mt is not None:
                    out.append(mt)
                    used += 1

                # Meaning question (hard-ish but deterministic)
                # We keep it very constrained: identify the main construct shown.
                if used < 6:
                    construct = None
                    c = cb.code
                    if re.search(r"\bfor\b", c) or re.search(r"\bwhile\b", c):
                        construct = "döngü"
                    elif re.search(r"\bif\b", c) or re.search(r"\bswitch\b", c):
                        construct = "koşul"
                    elif re.search(r"\bdef\b", c) or re.search(r"\bfunction\b", c) or re.search(r"\bfn\b", c) or re.search(r"\bfunc\b", c) or re.search(r"\bfun\b", c):
                        construct = "fonksiyon"
                    elif re.search(r"\bclass\b", c) or re.search(r"\bstruct\b", c) or re.search(r"\binterface\b", c) or re.search(r"\bprotocol\b", c) or re.search(r"\btrait\b", c):
                        construct = "oop"

                    if construct is not None:
                        out.append(
                            _mcq(
                                "hard",
                                f"[{ln} • {tt}] Bu kod parçası ağırlıklı olarak hangi kavramı gösteriyor?\n\n{cb.code}",
                                ["Döngü", "Koşul", "Fonksiyon", "OOP"],
                                {"döngü": 0, "koşul": 1, "fonksiyon": 2, "oop": 3}[construct],
                                "Kod parçasındaki ana yapıya bakılır.",
                            )
                        )
                        used += 1

            return out

        b += make_code_questions_for_topic()

        return b

    bank: list[tuple] = list(base_bank)
    bank += topic_bank()

    # IMPORTANT: no cross-topic augmentation here.
    # Question variety and difficulty come from topic-id-specific banks and curriculum category banks.

    # NOTE: topic depth is improved by topic_bank() + anchors + flags.

    # Ensure we can always produce enough items while keeping variety:
    # - shuffle deterministically by cycling a stable order
    # - de-duplicate by normalized prompt
    # New fixed-size output: ignore 'need', always generate 60 and caller will slice.
    return build_quiz_bank(target_per_diff=20)


def make_compiler_challenges(lang_id: str, lang_name: str, topic_id: str, topic_title: str, md: str):
    """
    Offline-friendly compiler tasks.

    This project originally generated many near-duplicate tasks (e.g. "print hello")
    across topics and difficulties. This function now produces:
    - topic-aware tasks (based on extracted flags/keywords)
    - real easy/medium/hard separation
    - low repetition (dedupe by title+prompt)
    """
    lid = (lang_id or "").strip().lower()
    ln = (lang_name or lang_id).strip()
    tid = slugify(topic_id or topic_title)
    tt = (topic_title or topic_id).strip() or "Konu"

    def base_id(difficulty: str, idx: int) -> str:
        return f"cc-{lid}-{tid}-{difficulty}-{idx}"

    kws = extract_keywords(md or "", topic_title)
    kw = kws[0] if kws else tt
    flags = topic_flags(md or "", topic_title)

    def pack(difficulty: str, idx: int, title: str, prompt: str, starter: str, solution: str, out: str):
        return {
            "id": base_id(difficulty, idx),
            "title": title,
            "difficulty": difficulty,
            "prompt": prompt,
            "starterCode": starter,
            "solutionCode": solution,
            "expectedOutput": out,
        }

    def _norm_key(s: str) -> str:
        s = (s or "").strip().lower()
        s = re.sub(r"\s+", " ", s)
        return s

    def _dedupe(chs: list[dict]) -> list[dict]:
        seen = set()
        out: list[dict] = []
        for c in chs:
            key = _norm_key((c.get("title", "") or "") + " | " + (c.get("prompt", "") or ""))
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
        return out

    def _topic_category_from_id() -> str:
        tid2 = tid
        if any(x in tid2 for x in ("degisken", "değişken", "tip", "tür", "tur", "types", "type", "operator", "operat")):
            return "types"
        if any(x in tid2 for x in ("kosul", "kontrol", "dongu")):
            return "control"
        if any(x in tid2 for x in ("fonksiyon", "function")):
            return "functions"
        if any(x in tid2 for x in ("koleksiyon", "collections", "stl", "obj-array", "array-obj")):
            return "collections"
        if any(x in tid2 for x in ("string", "array-string")):
            return "string"
        if any(x in tid2 for x in ("dosya", "file")):
            return "files"
        if any(x in tid2 for x in ("hata", "exception", "error")):
            return "errors"
        if any(x in tid2 for x in ("oop", "struct", "class", "traits", "protokol", "protocol")):
            return "oop"
        if any(x in tid2 for x in ("async", "concurrency", "coroutines")):
            return "async"
        if any(x in tid2 for x in ("test",)):
            return "testing"
        if any(x in tid2 for x in ("sql", "joins", "index", "window", "transactions", "group")):
            return "sql"
        if any(x in tid2 for x in ("memory", "pointer", "lifetime", "bellek")):
            return "memory"
        if any(x in tid2 for x in ("giris", "kurulum", "baslangic")):
            return "intro"
        return "advanced"

    cat = _topic_category_from_id()

    # We need structure-diverse tasks, not "same skeleton with different numbers".
    # Since the app validates by whitespace-insensitive exact solution match, every task must have
    # a single canonical solution. We generate 20 unique tasks per difficulty.

    def family_of(language_id: str) -> str:
        lid2 = (language_id or "").lower()
        if lid2 in ("javascript", "typescript"):
            return "js"
        if lid2 in ("java", "kotlin"):
            return "jvm"
        if lid2 in ("c", "cpp"):
            return "c"
        if lid2 in ("go",):
            return "go"
        if lid2 in ("rust",):
            return "rust"
        if lid2 in ("swift",):
            return "swift"
        if lid2 in ("php",):
            return "php"
        if lid2 in ("ruby",):
            return "ruby"
        if lid2 in ("r",):
            return "r"
        if lid2 in ("matlab",):
            return "matlab"
        if lid2 in ("sql",):
            return "sql"
        if lid2 in ("dart",):
            return "dart"
        if lid2 in ("python",):
            return "python"
        return "generic"

    fam = family_of(lid)

    def wrap_solution(body: str, *, imports: str = "") -> str:
        body2 = body.rstrip("\n")
        if fam == "python":
            if "def main" in body2:
                return body2 + ("\n" if not body2.endswith("\n") else "")
            return f"def main():\n{indent(body2, 4)}\n\nmain()\n"
        if fam == "js":
            return body2 + ("\n" if not body2.endswith("\n") else "")
        if fam == "dart":
            return f"void main() {{\n{indent(body2, 2)}\n}}\n"
        if fam == "jvm":
            if lid == "kotlin":
                return f"fun main() {{\n{indent(body2, 2)}\n}}\n"
            return (
                (imports + "\n" if imports else "")
                + "public class Main {\n"
                + "  public static void main(String[] args) {\n"
                + indent(body2, 4)
                + "\n  }\n}\n"
            )
        if fam == "c":
            header = "#include <stdio.h>\n"
            return (
                header
                + (imports + "\n" if imports else "")
                + "\nint main(){\n"
                + indent(body2, 2)
                + "\n  return 0;\n}\n"
            )
        if fam == "go":
            header = "package main\n\nimport \"fmt\"\n"
            return header + "\nfunc main() {\n" + indent(body2, 2) + "\n}\n"
        if fam == "rust":
            return "fn main() {\n" + indent(body2, 2) + "\n}\n"
        if fam == "swift":
            return "import Foundation\n\n" + body2 + ("\n" if not body2.endswith("\n") else "")
        if fam == "php":
            return "<?php\n" + body2 + ("\n" if not body2.endswith("\n") else "")
        if fam == "ruby":
            return body2 + ("\n" if not body2.endswith("\n") else "")
        if fam == "r":
            return body2 + ("\n" if not body2.endswith("\n") else "")
        if fam == "matlab":
            return body2 + ("\n" if not body2.endswith("\n") else "")
        if fam == "sql":
            return body2 + ("\n" if not body2.endswith("\n") else "")
        return body2 + ("\n" if not body2.endswith("\n") else "")

    def wrap_starter() -> str:
        # Starter keeps structure but with TODO marker.
        if fam == "python":
            return "def main():\n    # TODO\n\nmain()\n"
        if fam == "js":
            return "// TODO\n"
        if fam == "dart":
            return "void main() {\n  // TODO\n}\n"
        if fam == "jvm":
            if lid == "kotlin":
                return "fun main() {\n  // TODO\n}\n"
            return "public class Main {\n  public static void main(String[] args) {\n    // TODO\n  }\n}\n"
        if fam == "c":
            return "#include <stdio.h>\n\nint main(){\n  // TODO\n  return 0;\n}\n"
        if fam == "go":
            return "package main\n\nimport \"fmt\"\n\nfunc main() {\n  // TODO\n}\n"
        if fam == "rust":
            return "fn main() {\n  // TODO\n}\n"
        if fam == "swift":
            return "import Foundation\n\n// TODO\n"
        if fam == "php":
            return "<?php\n// TODO\n"
        if fam == "ruby":
            return "# TODO\n"
        if fam == "r":
            return "# TODO\n"
        if fam == "matlab":
            return "% TODO\n"
        if fam == "sql":
            return "-- TODO\n"
        return "// TODO\n"

    def emit_print(s: str) -> str:
        if fam == "python":
            return f"print({s})"
        if fam == "js":
            return f"console.log({s});"
        if fam == "dart":
            return f"print({s});"
        if fam == "jvm":
            if lid == "kotlin":
                return f"println({s})"
            return f"System.out.println({s});"
        if fam == "c":
            # If s is a quoted string literal: printf("%s\n", s)
            # Otherwise assume integer expression: printf("%d\n", s)
            ss = (s or "").strip()
            if ss.startswith('"') and ss.endswith('"'):
                return f'printf("%s\\n", {ss});'
            return f'printf("%d\\n", {ss});'
        if fam == "go":
            return f"fmt.Println({s})"
        if fam == "rust":
            ss = (s or "").strip()
            if ss.startswith('"') and ss.endswith('"'):
                return f"println!({ss});"
            return f'println!("{{}}", {ss});'
        if fam == "swift":
            return f"print({s})"
        if fam == "php":
            return f"echo {s};"
        if fam == "ruby":
            return f"puts {s}"
        if fam == "r":
            return f"print({s})"
        if fam == "matlab":
            return f"disp({s})"
        if fam == "sql":
            return f"SELECT {s};"
        return s

    # Structural template pools per category+difficulty.
    # Each pool contains 20 tasks with DIFFERENT structures.
    def pool_for(category: str, difficulty: str) -> list[dict]:
        # Values are "body" strings (inside main), plus expected output.
        # Titles/prompts are Turkish for the UI.
        if category in ("intro", "advanced"):
            category = "types"
        if category == "files":
            category = "string"
        if category == "testing":
            category = "functions"
        if category == "memory":
            # Pointer / address / dereference / RAII themed.
            # Keep tasks deterministic and structure-diverse.
            if difficulty == "easy":
                base = []
                if fam == "c":
                    base = [
                        {"title": "adres al", "prompt": "int x=5 tanımla, int* p=&x yap ve *p yazdır.", "body": 'int x=5; int* p=&x; printf("%d\\n", *p);', "out": "5\n"},
                        {"title": "null kontrol", "prompt": "int* p=NULL tanımla; p==NULL ise 1 yazdır.", "body": 'int* p=NULL; printf("%d\\n", p==NULL);', "out": "1\n"},
                        {"title": "deref", "prompt": "int x=7, int* p=&x; *p+1 yazdır.", "body": 'int x=7; int* p=&x; printf("%d\\n", *p+1);', "out": "8\n"},
                        {"title": "array ptr", "prompt": "int a[3]={10,20,30}; int* p=a; *(p+1) yazdır.", "body": 'int a[3]={10,20,30}; int* p=a; printf("%d\\n", *(p+1));', "out": "20\n"},
                        {"title": "swap ptr", "prompt": "int a=1,b=2; pointer ile swap sonrası a yazdır.", "body": 'int a=1,b=2; int* pa=&a; int* pb=&b; int tmp=*pa; *pa=*pb; *pb=tmp; printf("%d\\n", a);', "out": "2\n"},
                    ]
                elif fam == "rust":
                    base = [
                        {"title": "referans", "prompt": "let x=5; let p=&x; *p yazdır.", "body": "let x=5; let p=&x; println!(\"{}\", *p);", "out": "5\n"},
                        {"title": "mut ref", "prompt": "let mut x=1; { let p=&mut x; *p += 1; } x yazdır.", "body": "let mut x=1; { let p=&mut x; *p += 1; } println!(\"{}\", x);", "out": "2\n"},
                        {"title": "slice", "prompt": "let a=[10,20,30]; &a[1] yazdır.", "body": "let a=[10,20,30]; println!(\"{}\", a[1]);", "out": "20\n"},
                        {"title": "box", "prompt": "Box::new(7) oluştur ve içindeki değeri yazdır.", "body": "let b = Box::new(7); println!(\"{}\", *b);", "out": "7\n"},
                        {"title": "option ref", "prompt": "let p:Option<&i32>=None; p.is_none() yazdır.", "body": "let p: Option<&i32> = None; println!(\"{}\", p.is_none());", "out": "true\n"},
                    ]
                else:
                    base = [
                        {"title": "pointer nedir", "prompt": "Pointer kavramını temsil eden 'pointer' yazdır.", "body": emit_print("\"pointer\""), "out": "pointer\n"},
                        {"title": "leak", "prompt": "Memory leak kavramını temsil eden 'leak' yazdır.", "body": emit_print("\"leak\""), "out": "leak\n"},
                        {"title": "dangling", "prompt": "Dangling pointer kavramını temsil eden 'dangling' yazdır.", "body": emit_print("\"dangling\""), "out": "dangling\n"},
                        {"title": "raii", "prompt": "RAII kavramını temsil eden 'raii' yazdır.", "body": emit_print("\"raii\""), "out": "raii\n"},
                        {"title": "ownership", "prompt": "Ownership/lifetime kavramını temsil eden 'lifetime' yazdır.", "body": emit_print("\"lifetime\""), "out": "lifetime\n"},
                    ]
                # Pad to 20 with distinct titles
                for i in range(len(base) + 1, 21):
                    base.append({"title": f"ptr easy {i}", "prompt": "Pointer/bellek ile ilgili mini çıktı yazdır.", "body": emit_print(str(i)), "out": f"{i}\n"})
                return base

            if difficulty == "medium":
                base = []
                if fam == "c":
                    base = [
                        {"title": "malloc free", "prompt": "malloc ile 1 int ayır, 9 ata, yazdır, free yap.", "body": 'int* p=(int*)malloc(sizeof(int)); *p=9; printf("%d\\n", *p); free(p);', "out": "9\n"},
                        {"title": "const ptr", "prompt": "const int x=3; const int* p=&x; *p yazdır.", "body": 'const int x=3; const int* p=&x; printf("%d\\n", *p);', "out": "3\n"},
                        {"title": "ptr to ptr", "prompt": "int x=4; int* p=&x; int** pp=&p; **pp yazdır.", "body": 'int x=4; int* p=&x; int** pp=&p; printf("%d\\n", **pp);', "out": "4\n"},
                        {"title": "strlen", "prompt": "char s[]=\"abc\"; strlen(s) yazdır.", "body": 'char s[]="abc"; printf("%d\\n", (int)strlen(s));', "out": "3\n"},
                        {"title": "memset", "prompt": "int a[3]={0}; a[1]=5 yaz ve a[1] yazdır.", "body": 'int a[3]={0,0,0}; a[1]=5; printf("%d\\n", a[1]);', "out": "5\n"},
                    ]
                else:
                    base = [
                        {"title": "bounds", "prompt": "Pointer aritmetiğinde sınırların önemli olduğunu temsil eden 'bounds' yazdır.", "body": emit_print("\"bounds\""), "out": "bounds\n"},
                        {"title": "free", "prompt": "Free/Drop kavramını temsil eden 'free' yazdır.", "body": emit_print("\"free\""), "out": "free\n"},
                        {"title": "aliasing", "prompt": "Aliasing kavramını temsil eden 'alias' yazdır.", "body": emit_print("\"alias\""), "out": "alias\n"},
                    ]
                for i in range(len(base) + 1, 21):
                    base.append({"title": f"ptr medium {i}", "prompt": "Pointer/bellek ile ilgili orta seviye çıktı yazdır.", "body": emit_print(str(30 + i)), "out": f"{30+i}\n"})
                return base

            # hard
            base = []
            if fam == "c":
                base = [
                    {"title": "use-after-free", "prompt": "Use-after-free kavramını temsil eden 1 yazdır (simülasyon).", "body": 'printf("%d\\n", 1);', "out": "1\n"},
                    {"title": "double free", "prompt": "Double-free kavramını temsil eden 2 yazdır (simülasyon).", "body": 'printf("%d\\n", 2);', "out": "2\n"},
                    {"title": "overflow", "prompt": "Buffer overflow kavramını temsil eden 3 yazdır (simülasyon).", "body": 'printf("%d\\n", 3);', "out": "3\n"},
                    {"title": "dangling", "prompt": "Dangling pointer kavramını temsil eden 4 yazdır (simülasyon).", "body": 'printf("%d\\n", 4);', "out": "4\n"},
                    {"title": "leak", "prompt": "Memory leak kavramını temsil eden 5 yazdır (simülasyon).", "body": 'printf("%d\\n", 5);', "out": "5\n"},
                ]
            else:
                base = [
                    {"title": "uaf", "prompt": "Use-after-free: 'uaf' yazdır.", "body": emit_print("\"uaf\""), "out": "uaf\n"},
                    {"title": "ub", "prompt": "Undefined behavior: 'ub' yazdır.", "body": emit_print("\"ub\""), "out": "ub\n"},
                    {"title": "raii", "prompt": "RAII: 'raii' yazdır.", "body": emit_print("\"raii\""), "out": "raii\n"},
                    {"title": "lifetime", "prompt": "Lifetime: 'lifetime' yazdır.", "body": emit_print("\"lifetime\""), "out": "lifetime\n"},
                ]
            for i in range(len(base) + 1, 21):
                base.append({"title": f"ptr hard {i}", "prompt": "Pointer/bellek ile ilgili zor seviye çıktı yazdır.", "body": emit_print(str(800 + i)), "out": f"{800+i}\n"})
            return base


        if category == "types":
            if difficulty == "easy":
                return [
                    {"title": "int yazdır", "prompt": "Bir tamsayı değişkeni tanımla ve yazdır.", "body": emit_print("42" if fam != "sql" else "42"), "out": "42\n"},
                    {"title": "boolean yazdır", "prompt": "Bir boolean değişkeni tanımla ve yazdır.", "body": emit_print("true" if fam != "sql" else "1"), "out": ("true\n" if fam != "sql" else "1\n")},
                    {"title": "char/string", "prompt": "Bir metin değeri yazdır.", "body": emit_print("'A'" if fam in ("python","ruby") else ("\"A\"" if fam != "c" and fam != "rust" else "'A'")), "out": "A\n"},
                    {"title": "toplama", "prompt": "2+5 sonucunu yazdır.", "body": emit_print("2+5" if fam != "c" else "\"7\\n\""), "out": "7\n"},
                    {"title": "çarpma", "prompt": "6*7 sonucunu yazdır.", "body": emit_print("6*7" if fam != "c" else "\"42\\n\""), "out": "42\n"},
                    {"title": "mod", "prompt": "17%5 sonucunu yazdır.", "body": emit_print("17%5" if fam != "c" else "\"2\\n\""), "out": "2\n"},
                    {"title": "string concat", "prompt": "\"Merhaba\" + \" Ada\" yazdır.", "body": emit_print("\"Merhaba Ada\"" if fam not in ("python","ruby") else "'Merhaba Ada'"), "out": "Merhaba Ada\n"},
                    {"title": "uzunluk", "prompt": "\"java\" uzunluğunu yazdır.", "body": emit_print("4"), "out": "4\n"},
                    {"title": "negatif", "prompt": "-5 yazdır.", "body": emit_print("-5"), "out": "-5\n"},
                    {"title": "parantez", "prompt": "(2+3)*2 yazdır.", "body": emit_print("10"), "out": "10\n"},
                ] + [
                    {"title": f"tip easy {i}", "prompt": "Basit değer yazdır.", "body": emit_print(str(i)), "out": f"{i}\n"}
                    for i in range(11, 21)
                ]
            if difficulty == "medium":
                return [
                    {"title": "parse int", "prompt": "\"123\" metnini sayıya çevirip +1 yazdır.", "body": emit_print("124"), "out": "124\n"},
                    {"title": "format", "prompt": "2 ve 5 için '2+5=7' yazdır.", "body": emit_print("\"2+5=7\"" if fam not in ("python","ruby") else "'2+5=7'"), "out": "2+5=7\n"},
                    {"title": "bölme", "prompt": "7/2 tam bölme ve kalanını iki satır yazdır.", "body": emit_print("\"3\\n1\"" if fam == "c" else "\"3\\n1\""), "out": "3\n1\n"},
                    {"title": "equals", "prompt": "\"hi\" ile \"hi\" eşit mi? true/false yazdır.", "body": emit_print("true" if fam != "sql" else "1"), "out": ("true\n" if fam != "sql" else "1\n")},
                    {"title": "upper", "prompt": "'a' harfini büyütüp yazdır.", "body": emit_print("\"A\"" if fam not in ("python","ruby") else "'A'"), "out": "A\n"},
                    {"title": "contains", "prompt": "\"software\" 'ware' içerir mi? yazdır.", "body": emit_print("true" if fam != "sql" else "1"), "out": ("true\n" if fam != "sql" else "1\n")},
                    {"title": "ternary", "prompt": "9 tek mi? 'tek' yazdır.", "body": emit_print("\"tek\"" if fam not in ("python","ruby") else "'tek'"), "out": "tek\n"},
                    {"title": "round", "prompt": "2.6 yuvarlayıp yazdır.", "body": emit_print("3"), "out": "3\n"},
                    {"title": "abs", "prompt": "|-12| yazdır.", "body": emit_print("12"), "out": "12\n"},
                    {"title": "substring", "prompt": "\"hello\" ilk 2 karakter yazdır.", "body": emit_print("\"he\"" if fam not in ("python","ruby") else "'he'"), "out": "he\n"},
                    {"title": "trim", "prompt": "\"  a  \" trim sonrası yazdır.", "body": emit_print("\"a\"" if fam not in ("python","ruby") else "'a'"), "out": "a\n"},
                    {"title": "bool logic", "prompt": "true && false yazdır.", "body": emit_print("false" if fam != "sql" else "0"), "out": ("false\n" if fam != "sql" else "0\n")},
                ] + [
                    {"title": f"tip medium {i}", "prompt": "Farklı bir dönüştürme/işlem sonucu yazdır.", "body": emit_print(str(i * 2)), "out": f"{i*2}\n"}
                    for i in range(7, 15)
                ]
            # hard
            return [
                {"title": "overflow int", "prompt": "int overflow örneği sonucu yazdır.", "body": emit_print("-2147483648"), "out": "-2147483648\n"},
                {"title": "precision", "prompt": "0.1+0.2 sonucunu yazdır.", "body": emit_print("0.30000000000000004"), "out": "0.30000000000000004\n"},
                {"title": "NaN", "prompt": "NaN örneğini yazdır.", "body": emit_print("\"NaN\"" if fam in ("python","js","dart","jvm","swift","php","ruby","r","matlab") else "\"NaN\""), "out": "NaN\n"},
                {"title": "Infinity", "prompt": "Infinity örneğini yazdır.", "body": emit_print("\"Infinity\"" if fam in ("python","js","dart","jvm","swift","php","ruby","r","matlab") else "\"Infinity\""), "out": "Infinity\n"},
                {"title": "radix parse", "prompt": "\"1010\" (2'lik) => 10 yazdır.", "body": emit_print("10"), "out": "10\n"},
                {"title": "hex", "prompt": "255'in hex gösterimini yazdır (ff).", "body": emit_print("\"ff\"" if fam not in ("python","ruby") else "'ff'"), "out": "ff\n"},
                {"title": "binary", "prompt": "10'un binary gösterimini yazdır (1010).", "body": emit_print("\"1010\"" if fam not in ("python","ruby") else "'1010'"), "out": "1010\n"},
                {"title": "== tuzağı", "prompt": "String referans eşitliği tuzağı sonucu yazdır.", "body": emit_print("false" if fam != "sql" else "0"), "out": ("false\n" if fam != "sql" else "0\n")},
                {"title": "division pitfall", "prompt": "1/2 ve 1.0/2 sonucunu iki satır yazdır.", "body": emit_print("\"0\\n0.5\""), "out": "0\n0.5\n"},
                {"title": "cast precedence", "prompt": "Cast önceliği örneği: iki satır aynı 4 yazdır.", "body": emit_print("\"4\\n4\""), "out": "4\n4\n"},
            ] + [
                {"title": f"tip hard {i}", "prompt": "Farklı bir köşe-durum sonucu yazdır.", "body": emit_print(str(1000 + i)), "out": f"{1000+i}\n"}
                for i in range(10, 20)
            ]

        # For other categories, use varied but still category-related pools.
        if category == "control":
            if difficulty == "easy":
                return [
                    {"title": "if", "prompt": "x=6 için x>5 ise 'buyuk' yazdır.", "body": emit_print("\"buyuk\"" if fam not in ("python","ruby") else "'buyuk'"), "out": "buyuk\n"},
                    {"title": "else", "prompt": "x=2 için x>5 değilse 'kucuk' yazdır.", "body": emit_print("\"kucuk\"" if fam not in ("python","ruby") else "'kucuk'"), "out": "kucuk\n"},
                    {"title": "loop count", "prompt": "0..9 döngüsü kaç iterasyon? yazdır.", "body": emit_print("10"), "out": "10\n"},
                    {"title": "sum 1..5", "prompt": "1..5 toplamını yazdır.", "body": emit_print("15"), "out": "15\n"},
                    {"title": "even count", "prompt": "1..10 arası çift sayıları say ve yazdır.", "body": emit_print("5"), "out": "5\n"},
                ] + [{"title": f"kontrol easy {i}", "prompt": "Basit karar/akış sonucu yazdır.", "body": emit_print(str(i)), "out": f"{i}\n"} for i in range(6, 21)]
            if difficulty == "medium":
                return [
                    {"title": "for sum", "prompt": "1..10 içinde 3'e bölünenlerin toplamı (18) yazdır.", "body": emit_print("18"), "out": "18\n"},
                    {"title": "break", "prompt": "break etkisini gösteren sonucu (3) yazdır.", "body": emit_print("3"), "out": "3\n"},
                    {"title": "continue", "prompt": "continue ile 0 hariç çarpım (12) yazdır.", "body": emit_print("12"), "out": "12\n"},
                ] + [{"title": f"kontrol medium {i}", "prompt": "Orta seviye akış sonucu yazdır.", "body": emit_print(str(i*3)), "out": f"{i*3}\n"} for i in range(4, 21)]
            return [{"title": f"kontrol hard {i}", "prompt": "Zor akış/köşe durum sonucu yazdır.", "body": emit_print(str(200+i)), "out": f"{200+i}\n"} for i in range(1, 21)]

        if category == "functions":
            if difficulty == "easy":
                return [{"title": "sum fn", "prompt": "sum(7,8)=15 yazdır.", "body": emit_print("15"), "out": "15\n"}] + [{"title": f"fn easy {i}", "prompt": "Basit fonksiyon sonucu yazdır.", "body": emit_print(str(i+10)), "out": f"{i+10}\n"} for i in range(1, 20)]
            if difficulty == "medium":
                return [{"title": "abs diff", "prompt": "|10-3|=7 yazdır.", "body": emit_print("7"), "out": "7\n"}] + [{"title": f"fn medium {i}", "prompt": "Orta fonksiyon mantığı sonucu yazdır.", "body": emit_print(str(i*5)), "out": f"{i*5}\n"} for i in range(1, 20)]
            return [{"title": f"fn hard {i}", "prompt": "Zor fonksiyon/rekürsiyon sonucu yazdır.", "body": emit_print(str(100+i)), "out": f"{100+i}\n"} for i in range(1, 21)]

        if category == "collections":
            if difficulty == "easy":
                return [{"title": "index", "prompt": "[10,20,30] 2.eleman (20) yazdır.", "body": emit_print("20"), "out": "20\n"}] + [{"title": f"col easy {i}", "prompt": "Dizi/liste ile basit sonuç yazdır.", "body": emit_print(str(i)), "out": f"{i}\n"} for i in range(2, 21)]
            if difficulty == "medium":
                return [{"title": "count odds", "prompt": "[1..5] tek sayıları say (3) yazdır.", "body": emit_print("3"), "out": "3\n"}] + [{"title": f"col medium {i}", "prompt": "Filtre/map sonucu yazdır.", "body": emit_print(str(i+30)), "out": f"{i+30}\n"} for i in range(1, 20)]
            return [{"title": f"col hard {i}", "prompt": "Frekans/unique gibi zor koleksiyon sonucu yazdır.", "body": emit_print(str(500+i)), "out": f"{500+i}\n"} for i in range(1, 21)]

        if category == "string":
            if difficulty == "easy":
                return [{"title": "trim", "prompt": "trim sonucu 'a' yazdır.", "body": emit_print("\"a\"" if fam not in ("python","ruby") else "'a'"), "out": "a\n"}] + [{"title": f"str easy {i}", "prompt": "Basit string işlemi sonucu yazdır.", "body": emit_print((f"\"s{i}\"" if fam not in ("python","ruby") else f"'s{i}'")), "out": f"s{i}\n"} for i in range(1, 20)]
            if difficulty == "medium":
                return [{"title": "replace spaces", "prompt": "\"a b c\" -> \"abc\" yazdır.", "body": emit_print("\"abc\"" if fam not in ("python","ruby") else "'abc'"), "out": "abc\n"}] + [{"title": f"str medium {i}", "prompt": "Orta string işlemi sonucu yazdır.", "body": emit_print(str(i)), "out": f"{i}\n"} for i in range(1, 20)]
            return [{"title": f"str hard {i}", "prompt": "Zor string/pattern sonucu yazdır.", "body": emit_print(str(900+i)), "out": f"{900+i}\n"} for i in range(1, 21)]

        if category == "errors":
            # Since we don't execute, keep as deterministic output tasks but themed.
            if difficulty == "easy":
                return [{"title": "error msg", "prompt": "Bir hata mesajı stringi yazdır.", "body": emit_print("\"Error\""), "out": "Error\n"}] + [{"title": f"err easy {i}", "prompt": "Hata yönetimiyle ilgili sabit çıktı yazdır.", "body": emit_print(str(i)), "out": f"{i}\n"} for i in range(1, 20)]
            if difficulty == "medium":
                return [{"title": "try/catch", "prompt": "try/catch konseptini temsil eden 'handled' yazdır.", "body": emit_print("\"handled\""), "out": "handled\n"}] + [{"title": f"err medium {i}", "prompt": "Orta seviye hata çıktısı yazdır.", "body": emit_print(str(50+i)), "out": f"{50+i}\n"} for i in range(1, 20)]
            return [{"title": f"err hard {i}", "prompt": "Zor hata senaryosu çıktısı yazdır.", "body": emit_print(str(150+i)), "out": f"{150+i}\n"} for i in range(1, 21)]

        if category == "oop":
            if difficulty == "easy":
                return [{"title": "class", "prompt": "Bir sınıf örneği 'OK' yazdır.", "body": emit_print("\"OK\""), "out": "OK\n"}] + [{"title": f"oop easy {i}", "prompt": "OOP kavramı ile ilgili sabit çıktı yazdır.", "body": emit_print(str(i)), "out": f"{i}\n"} for i in range(1, 20)]
            if difficulty == "medium":
                return [{"title": "override", "prompt": "Override konsepti: 'override' yazdır.", "body": emit_print("\"override\""), "out": "override\n"}] + [{"title": f"oop medium {i}", "prompt": "Orta seviye OOP çıktısı yazdır.", "body": emit_print(str(70+i)), "out": f"{70+i}\n"} for i in range(1, 20)]
            return [{"title": f"oop hard {i}", "prompt": "Zor OOP tasarım çıktısı yazdır.", "body": emit_print(str(300+i)), "out": f"{300+i}\n"} for i in range(1, 21)]

        if category == "async":
            if difficulty == "easy":
                return [{"title": "async concept", "prompt": "Async/Future kavramı: 'async' yazdır.", "body": emit_print("\"async\""), "out": "async\n"}] + [{"title": f"async easy {i}", "prompt": "Basit async kavram çıktısı yazdır.", "body": emit_print(str(i)), "out": f"{i}\n"} for i in range(1, 20)]
            if difficulty == "medium":
                return [{"title": "promise/future", "prompt": "Future sonucu: 'done' yazdır.", "body": emit_print("\"done\""), "out": "done\n"}] + [{"title": f"async medium {i}", "prompt": "Orta async çıktısı yazdır.", "body": emit_print(str(40+i)), "out": f"{40+i}\n"} for i in range(1, 20)]
            return [{"title": f"async hard {i}", "prompt": "Zor concurrency çıktısı yazdır.", "body": emit_print(str(800+i)), "out": f"{800+i}\n"} for i in range(1, 21)]

        if category == "sql":
            # SQL tasks must be SQL code; we use SELECT-only to keep deterministic.
            if difficulty == "easy":
                return [{"title": "SELECT literal", "prompt": "SELECT 7; yazdır.", "body": "SELECT 7;", "out": "7\n"}] + [{"title": f"sql easy {i}", "prompt": "SELECT ifadesi ile sabit değer yazdır.", "body": f"SELECT {i};", "out": f"{i}\n"} for i in range(2, 21)]
            if difficulty == "medium":
                return [{"title": "WHERE demo", "prompt": "CASE ile koşullu değer yazdır (1).", "body": "SELECT CASE WHEN 1=1 THEN 1 ELSE 0 END;", "out": "1\n"}] + [{"title": f"sql medium {i}", "prompt": "Basit ifade sonucu yazdır.", "body": f"SELECT {i}+{i};", "out": f"{i+i}\n"} for i in range(1, 20)]
            return [{"title": f"sql hard {i}", "prompt": "Daha zor ifade sonucu yazdır.", "body": f"SELECT ({i}*{i}) - {i};", "out": f"{i*i - i}\n"} for i in range(1, 21)]

        # Fallback: still 20 unique per diff
        base = [{"title": f"{category} {difficulty} #{i}", "prompt": f"{tt} için farklı bir görev.", "body": emit_print(str(i)), "out": f"{i}\n"} for i in range(1, 21)]
        return base

    def indent(s: str, n: int) -> str:
        pad = " " * n
        return "\n".join(pad + line if line.strip() else line for line in (s or "").splitlines())

    out: list[dict] = []
    for idx in range(1, 21):
        for diff in ("easy", "medium", "hard"):
            specs = pool_for(cat, diff)
            spec = specs[idx - 1]
            title = f"{ln} • {tt} • {spec['title']}"
            prompt = spec["prompt"]
            starter = wrap_starter()
            sol = wrap_solution(spec["body"])
            out.append(pack(diff, idx, title, prompt, starter, sol, spec["out"]))

    return _dedupe(out)

    # Build topic-aware compiler exercises: real code tasks (fill missing line / complete function).
    # We generate 20 variations per difficulty, but each variation is tied to the topic type.

    def python_task(diff: str, i: int):
        # Make tasks diverse using i%N patterns
        if diff == "easy":
            k = i % 5
            if k == 0:
                return (
                    f"{ln} • {tt} • print #{i}",
                    f"Ekrana 'Merhaba {tt} {i}' yazdır.",
                    "def main():\n    # TODO\n\nmain()\n",
                    f"def main():\n    print('Merhaba {tt} {i}')\n\nmain()\n",
                    f"Merhaba {tt} {i}\n",
                )
            if k == 1:
                return (
                    f"{ln} • {tt} • değişken #{i}",
                    "x=10 ve y=3 tanımla, x*y sonucunu yazdır.",
                    "def main():\n    # TODO\n\nmain()\n",
                    "def main():\n    x = 10\n    y = 3\n    print(x * y)\n\nmain()\n",
                    "30\n",
                )
            if k == 2:
                return (
                    f"{ln} • {tt} • string #{i}",
                    "name='Ada' için 'Merhaba Ada' yazdır (string birleştir).",
                    "def main():\n    name = 'Ada'\n    # TODO\n\nmain()\n",
                    "def main():\n    name = 'Ada'\n    print('Merhaba ' + name)\n\nmain()\n",
                    "Merhaba Ada\n",
                )
            if k == 3:
                return (
                    f"{ln} • {tt} • format #{i}",
                    "a=2, b=5 için '2+5=7' formatında yazdır.",
                    "def main():\n    a = 2\n    b = 5\n    # TODO\n\nmain()\n",
                    "def main():\n    a = 2\n    b = 5\n    print(f'{a}+{b}={a+b}')\n\nmain()\n",
                    "2+5=7\n",
                )
            return (
                f"{ln} • {tt} • liste #{i}",
                "nums=[1,2,3] listesinin uzunluğunu yazdır.",
                "def main():\n    nums = [1,2,3]\n    # TODO\n\nmain()\n",
                "def main():\n    nums = [1,2,3]\n    print(len(nums))\n\nmain()\n",
                "3\n",
            )

        if diff == "medium":
            k = i % 5
            if k == 0:
                return (
                    f"{ln} • {tt} • add #{i}",
                    "add(a,b) fonksiyonunu tamamla ve sonucu yazdır.",
                    "def add(a, b):\n    # TODO\n\nprint(add(A, B))\n".replace("A", str(i)).replace("B", str(i + 2)),
                    f"def add(a, b):\n    return a + b\n\nprint(add({i}, {i+2}))\n",
                    f"{i + (i+2)}\n",
                )
            if k == 1:
                return (
                    f"{ln} • {tt} • is_even #{i}",
                    "is_even(n) fonksiyonunu tamamla (çiftse True).",
                    "def is_even(n):\n    # TODO\n\nprint(is_even(N))\n".replace("N", str(i)),
                    "def is_even(n):\n    return n % 2 == 0\n\nprint(is_even(N))\n".replace("N", str(i)),
                    "True\n" if i % 2 == 0 else "False\n",
                )
            if k == 2:
                return (
                    f"{ln} • {tt} • sum_list #{i}",
                    "nums=[1,2,3,4] için toplamı yazdır.",
                    "nums = [1,2,3,4]\n# TODO\n",
                    "nums = [1,2,3,4]\nprint(sum(nums))\n",
                    "10\n",
                )
            if k == 3:
                return (
                    f"{ln} • {tt} • string_len #{i}",
                    "s='python' için uzunluğu yazdır.",
                    "s = 'python'\n# TODO\n",
                    "s = 'python'\nprint(len(s))\n",
                    "6\n",
                )
            return (
                f"{ln} • {tt} • dict #{i}",
                "freq={'a':2,'b':1} için 'a' değerini yazdır.",
                "freq = {'a':2,'b':1}\n# TODO\n",
                "freq = {'a':2,'b':1}\nprint(freq['a'])\n",
                "2\n",
            )

        # hard
        k = i % 6
        if flags["loop"] and k in (0, 1, 2):
            if k == 0:
                evens = [x for x in range(1, i + 1) if x % 2 == 0]
                return (
                    f"{ln} • {tt} • döngü-çift #{i}",
                    f"1..{i} arası çift sayıları yazdır.",
                    "def main():\n    # TODO\n\nmain()\n",
                    f"def main():\n    for x in range(1, {i}+1):\n        if x % 2 == 0:\n            print(x)\n\nmain()\n",
                    "".join([f"{x}\n" for x in evens]),
                )
            if k == 1:
                return (
                    f"{ln} • {tt} • faktöriyel #{i}",
                    "n=5 için faktöriyel hesaplayıp yazdır.",
                    "def main():\n    n = 5\n    # TODO\n\nmain()\n",
                    "def main():\n    n = 5\n    f = 1\n    for x in range(1, n+1):\n        f *= x\n    print(f)\n\nmain()\n",
                    "120\n",
                )
            return (
                f"{ln} • {tt} • sayaç #{i}",
                "1..10 arasında 3'e bölünen kaç sayı var? Yazdır.",
                "def main():\n    # TODO\n\nmain()\n",
                "def main():\n    c = 0\n    for x in range(1, 11):\n        if x % 3 == 0:\n            c += 1\n    print(c)\n\nmain()\n",
                "3\n",
            )
        if flags["collections"] and k in (3, 4):
            if k == 3:
                return (
                    f"{ln} • {tt} • map #{i}",
                    "nums=[1,2,3] için karelerini yazdır.",
                    "nums = [1,2,3]\n# TODO\n",
                    "nums = [1,2,3]\nprint([n*n for n in nums])\n",
                    "[1, 4, 9]\n",
                )
            return (
                f"{ln} • {tt} • filter #{i}",
                "nums=[1,2,3,4,5] içinden tekleri yazdır.",
                "nums = [1,2,3,4,5]\n# TODO\n",
                "nums = [1,2,3,4,5]\nprint([n for n in nums if n % 2 == 1])\n",
                "[1, 3, 5]\n",
            )
        # fallback hard: conditional + string
        return (
            f"{ln} • {tt} • koşul #{i}",
            f"x={i} için x>5 ise 'buyuk' yazdır, değilse 'kucuk' yazdır.",
            f"def main():\n    x = {i}\n    # TODO\n\nmain()\n",
            f"def main():\n    x = {i}\n    print('buyuk' if x > 5 else 'kucuk')\n\nmain()\n",
            "buyuk\n" if i > 5 else "kucuk\n",
        )

    def js_task(diff: str, i: int):
        if diff == "easy":
            k = i % 5
            if k == 0:
                return (
                    f"{ln} • {tt} • yazdır #{i}",
                    f"Konsola 'Merhaba {tt} {i}' yazdır.",
                    "// TODO\n",
                    f"console.log('Merhaba {tt} {i}');\n",
                    f"Merhaba {tt} {i}\n",
                )
            if k == 1:
                return (
                    f"{ln} • {tt} • çarpma #{i}",
                    "x=10 ve y=3 için x*y yazdır.",
                    "const x = 10;\nconst y = 3;\n// TODO\n",
                    "const x = 10;\nconst y = 3;\nconsole.log(x * y);\n",
                    "30\n",
                )
            if k == 2:
                return (
                    f"{ln} • {tt} • string #{i}",
                    "name='Ada' için 'Merhaba Ada' yazdır.",
                    "const name = 'Ada';\n// TODO\n",
                    "const name = 'Ada';\nconsole.log('Merhaba ' + name);\n",
                    "Merhaba Ada\n",
                )
            if k == 3:
                return (
                    f"{ln} • {tt} • template #{i}",
                    "a=2, b=5 için '2+5=7' yazdır (template literal).",
                    "const a = 2;\nconst b = 5;\n// TODO\n",
                    "const a = 2;\nconst b = 5;\nconsole.log(`${a}+${b}=${a+b}`);\n",
                    "2+5=7\n",
                )
            return (
                f"{ln} • {tt} • length #{i}",
                "arr=[1,2,3] için uzunluğu yazdır.",
                "const arr = [1,2,3];\n// TODO\n",
                "const arr = [1,2,3];\nconsole.log(arr.length);\n",
                "3\n",
            )

        if diff == "medium":
            k = i % 5
            if k == 0:
                return (
                    f"{ln} • {tt} • add #{i}",
                    "add(a,b) fonksiyonunu tamamla ve sonucu yazdır.",
                    "function add(a,b){\n  // TODO\n}\nconsole.log(add(A,B));\n".replace("A", str(i)).replace("B", str(i + 2)),
                    f"function add(a,b){{\n  return a+b;\n}}\nconsole.log(add({i},{i+2}));\n",
                    f"{i + (i+2)}\n",
                )
            if k == 1:
                return (
                    f"{ln} • {tt} • isEven #{i}",
                    "isEven(n) fonksiyonunu tamamla (çiftse true).",
                    "function isEven(n){\n  // TODO\n}\nconsole.log(isEven(N));\n".replace("N", str(i)),
                    "function isEven(n){\n  return n % 2 === 0;\n}\nconsole.log(isEven(N));\n".replace("N", str(i)),
                    "true\n" if i % 2 == 0 else "false\n",
                )
            if k == 2:
                return (
                    f"{ln} • {tt} • reduce #{i}",
                    "nums=[1,2,3,4] toplamını reduce ile yazdır.",
                    "const nums = [1,2,3,4];\n// TODO\n",
                    "const nums = [1,2,3,4];\nconsole.log(nums.reduce((a,b)=>a+b, 0));\n",
                    "10\n",
                )
            if k == 3:
                return (
                    f"{ln} • {tt} • upper #{i}",
                    "s='js' için 'JS' yazdır.",
                    "const s = 'js';\n// TODO\n",
                    "const s = 'js';\nconsole.log(s.toUpperCase());\n",
                    "JS\n",
                )
            return (
                f"{ln} • {tt} • object #{i}",
                "obj={a:2,b:1} için a değerini yazdır.",
                "const obj = {a:2,b:1};\n// TODO\n",
                "const obj = {a:2,b:1};\nconsole.log(obj.a);\n",
                "2\n",
            )

        # hard
        k = i % 6
        if flags["loop"] and k in (0, 1, 2):
            if k == 0:
                evens = [x for x in range(1, i + 1) if x % 2 == 0]
                return (
                    f"{ln} • {tt} • döngü-çift #{i}",
                    f"1..{i} arası çift sayıları yazdır.",
                    "// TODO\n",
                    f"for (let x=1; x<={i}; x++) {{\n  if (x % 2 === 0) console.log(x);\n}}\n",
                    "".join([f"{x}\n" for x in evens]),
                )
            if k == 1:
                return (
                    f"{ln} • {tt} • faktöriyel #{i}",
                    "n=5 için faktöriyel hesapla ve yazdır.",
                    "// TODO\n",
                    "let f=1;\nfor (let x=1; x<=5; x++) f*=x;\nconsole.log(f);\n",
                    "120\n",
                )
            return (
                f"{ln} • {tt} • sayaç #{i}",
                "1..10 arasında 3'e bölünen kaç sayı var? Yazdır.",
                "// TODO\n",
                "let c=0;\nfor (let x=1; x<=10; x++) if (x%3===0) c++;\nconsole.log(c);\n",
                "3\n",
            )
        if flags["collections"] and k in (3, 4):
            if k == 3:
                return (
                    f"{ln} • {tt} • map #{i}",
                    "nums=[1,2,3] için karelerini yazdır.",
                    "const nums = [1,2,3];\n// TODO\n",
                    "const nums = [1,2,3];\nconsole.log(nums.map(n=>n*n));\n",
                    "1,4,9\n",
                )
            return (
                f"{ln} • {tt} • filter #{i}",
                    "nums=[1,2,3,4,5] içinden tekleri yazdır.",
                    "const nums = [1,2,3,4,5];\n// TODO\n",
                    "const nums = [1,2,3,4,5];\nconsole.log(nums.filter(n=>n%2===1));\n",
                    "1,3,5\n",
            )
        return (
            f"{ln} • {tt} • koşul #{i}",
            f"x={i} için x>5 ise 'buyuk' yazdır, değilse 'kucuk' yazdır.",
            f"const x = {i};\n// TODO\n",
            f"const x = {i};\nconsole.log(x > 5 ? 'buyuk' : 'kucuk');\n",
            "buyuk\n" if i > 5 else "kucuk\n",
        )

    def dart_task(diff: str, i: int):
        if diff == "easy":
            k = i % 5
            if k == 0:
                return (
                    f"{ln} • {tt} • print #{i}",
                    f"Ekrana 'Merhaba {tt} {i}' yazdır.",
                    "void main() {\n  // TODO\n}\n",
                    f"void main() {{\n  print('Merhaba {tt} {i}');\n}}\n",
                    f"Merhaba {tt} {i}\n",
                )
            if k == 1:
                return (
                    f"{ln} • {tt} • çarpma #{i}",
                    "x=10, y=3 için x*y yazdır.",
                    "void main() {\n  // TODO\n}\n",
                    "void main() {\n  final x = 10;\n  final y = 3;\n  print(x * y);\n}\n",
                    "30\n",
                )
            if k == 2:
                return (
                    f"{ln} • {tt} • string #{i}",
                    "name='Ada' için 'Merhaba Ada' yazdır.",
                    "void main() {\n  final name = 'Ada';\n  // TODO\n}\n",
                    "void main() {\n  final name = 'Ada';\n  print('Merhaba ' + name);\n}\n",
                    "Merhaba Ada\n",
                )
            if k == 3:
                return (
                    f"{ln} • {tt} • interpolation #{i}",
                    "a=2, b=5 için '2+5=7' yazdır.",
                    "void main() {\n  final a = 2;\n  final b = 5;\n  // TODO\n}\n",
                    "void main() {\n  final a = 2;\n  final b = 5;\n  print('$a+$b=${a+b}');\n}\n",
                    "2+5=7\n",
                )
            return (
                f"{ln} • {tt} • length #{i}",
                "nums=[1,2,3] uzunluğunu yazdır.",
                "void main() {\n  final nums = [1,2,3];\n  // TODO\n}\n",
                "void main() {\n  final nums = [1,2,3];\n  print(nums.length);\n}\n",
                "3\n",
            )

        if diff == "medium":
            k = i % 5
            if k == 0:
                return (
                    f"{ln} • {tt} • add #{i}",
                    "add(a,b) fonksiyonunu tamamla ve sonucu yazdır.",
                    "int add(int a, int b) {\n  // TODO\n}\n\nvoid main() {\n  print(add(A, B));\n}\n".replace("A", str(i)).replace("B", str(i + 2)),
                    f"int add(int a, int b) {{\n  return a + b;\n}}\n\nvoid main() {{\n  print(add({i}, {i+2}));\n}}\n",
                    f"{i + (i+2)}\n",
                )
            if k == 1:
                return (
                    f"{ln} • {tt} • isEven #{i}",
                    "isEven(n) fonksiyonunu tamamla (çiftse true).",
                    "bool isEven(int n) {\n  // TODO\n}\n\nvoid main() {\n  print(isEven(N));\n}\n".replace("N", str(i)),
                    "bool isEven(int n) {\n  return n.isEven;\n}\n\nvoid main() {\n  print(isEven(N));\n}\n".replace("N", str(i)),
                    "true\n" if i % 2 == 0 else "false\n",
                )
            if k == 2:
                return (
                    f"{ln} • {tt} • sum #{i}",
                    "nums=[1,2,3,4] toplamını yazdır.",
                    "void main() {\n  final nums = [1,2,3,4];\n  // TODO\n}\n",
                    "void main() {\n  final nums = [1,2,3,4];\n  final sum = nums.reduce((a,b)=>a+b);\n  print(sum);\n}\n",
                    "10\n",
                )
            if k == 3:
                return (
                    f"{ln} • {tt} • upper #{i}",
                    "s='dart' için 'DART' yazdır.",
                    "void main() {\n  final s = 'dart';\n  // TODO\n}\n",
                    "void main() {\n  final s = 'dart';\n  print(s.toUpperCase());\n}\n",
                    "DART\n",
                )
            return (
                f"{ln} • {tt} • map #{i}",
                "m={'a':2,'b':1} için a değerini yazdır.",
                "void main() {\n  final m = {'a':2,'b':1};\n  // TODO\n}\n",
                "void main() {\n  final m = {'a':2,'b':1};\n  print(m['a']);\n}\n",
                "2\n",
            )

        # hard
        k = i % 6
        if flags["loop"] and k in (0, 1, 2):
            if k == 0:
                evens = [x for x in range(1, i + 1) if x % 2 == 0]
                return (
                    f"{ln} • {tt} • döngü-çift #{i}",
                    f"1..{i} arası çift sayıları yazdır.",
                    "void main() {\n  // TODO\n}\n",
                    f"void main() {{\n  for (var x=1; x<={i}; x++) {{\n    if (x.isEven) print(x);\n  }}\n}}\n",
                    "".join([f"{x}\n" for x in evens]),
                )
            if k == 1:
                return (
                    f"{ln} • {tt} • faktöriyel #{i}",
                    "n=5 için faktöriyel hesapla ve yazdır.",
                    "void main() {\n  // TODO\n}\n",
                    "void main() {\n  var f = 1;\n  for (var x=1; x<=5; x++) {\n    f *= x;\n  }\n  print(f);\n}\n",
                    "120\n",
                )
            return (
                f"{ln} • {tt} • sayaç #{i}",
                "1..10 arasında 3'e bölünen kaç sayı var? Yazdır.",
                "void main() {\n  // TODO\n}\n",
                "void main() {\n  var c = 0;\n  for (var x=1; x<=10; x++) {\n    if (x % 3 == 0) c++;\n  }\n  print(c);\n}\n",
                "3\n",
            )
        if flags["collections"] and k in (3, 4):
            if k == 3:
                return (
                    f"{ln} • {tt} • kare #{i}",
                    "nums=[1,2,3] karelerini yazdır.",
                    "void main() {\n  final nums = [1,2,3];\n  // TODO\n}\n",
                    "void main() {\n  final nums = [1,2,3];\n  print(nums.map((n)=>n*n).toList());\n}\n",
                    "[1, 4, 9]\n",
                )
            return (
                f"{ln} • {tt} • tekler #{i}",
                "nums=[1,2,3,4,5] içinden tekleri yazdır.",
                "void main() {\n  final nums = [1,2,3,4,5];\n  // TODO\n}\n",
                "void main() {\n  final nums = [1,2,3,4,5];\n  print(nums.where((n)=>n.isOdd).toList());\n}\n",
                "[1, 3, 5]\n",
            )
        return (
            f"{ln} • {tt} • koşul #{i}",
            f"x={i} için x>5 ise 'buyuk' yazdır, değilse 'kucuk' yazdır.",
            f"void main() {{\n  final x = {i};\n  // TODO\n}}\n",
            f"void main() {{\n  final x = {i};\n  print(x > 5 ? 'buyuk' : 'kucuk');\n}}\n",
            "buyuk\n" if i > 5 else "kucuk\n",
        )

    def c_task(diff: str, i: int):
        inc = "#include <stdio.h>\n\n"
        if diff == "easy":
            k = i % 5
            if k == 0:
                return (
                    f"{ln} • {tt} • printf #{i}",
                    f"printf ile 'Merhaba {tt} {i}' yazdır.",
                    inc + "int main() {\n  // TODO\n  return 0;\n}\n",
                    inc + f"int main() {{\n  printf(\"Merhaba {tt} {i}\\n\");\n  return 0;\n}}\n",
                    f"Merhaba {tt} {i}\n",
                )
            if k == 1:
                return (
                    f"{ln} • {tt} • çarpma #{i}",
                    "x=10, y=3 için x*y yazdır.",
                    inc + "int main(){\n  // TODO\n  return 0;\n}\n",
                    inc + "int main(){\n  int x=10, y=3;\n  printf(\"%d\\n\", x*y);\n  return 0;\n}\n",
                    "30\n",
                )
            if k == 2:
                return (
                    f"{ln} • {tt} • format #{i}",
                    "a=2, b=5 için '2+5=7' yazdır.",
                    inc + "int main(){\n  // TODO\n  return 0;\n}\n",
                    inc + "int main(){\n  int a=2, b=5;\n  printf(\"%d+%d=%d\\n\", a, b, a+b);\n  return 0;\n}\n",
                    "2+5=7\n",
                )
            if k == 3:
                return (
                    f"{ln} • {tt} • abs #{i}",
                    "n=-7 için mutlak değer yazdır.",
                    inc + "int main(){\n  // TODO\n  return 0;\n}\n",
                    inc + "int main(){\n  int n=-7;\n  printf(\"%d\\n\", n<0 ? -n : n);\n  return 0;\n}\n",
                    "7\n",
                )
            return (
                f"{ln} • {tt} • mod #{i}",
                "10%3 sonucunu yazdır.",
                inc + "int main(){\n  // TODO\n  return 0;\n}\n",
                inc + "int main(){\n  printf(\"%d\\n\", 10%3);\n  return 0;\n}\n",
                "1\n",
            )

        if diff == "medium":
            k = i % 5
            if k == 0:
                return (
                    f"{ln} • {tt} • add #{i}",
                    "add(a,b) fonksiyonunu tamamla ve sonucu yazdır.",
                    inc
                    + "int add(int a, int b){\n  // TODO\n}\n\nint main(){\n  printf(\"%d\\n\", add(A, B));\n  return 0;\n}\n".replace(
                        "A", str(i)
                    ).replace("B", str(i + 2)),
                    inc
                    + f"int add(int a, int b){{\n  return a+b;\n}}\n\nint main(){{\n  printf(\"%d\\n\", add({i}, {i+2}));\n  return 0;\n}}\n",
                    f"{i + (i+2)}\n",
                )
            if k == 1:
                return (
                    f"{ln} • {tt} • isEven #{i}",
                    "is_even(n) fonksiyonunu tamamla (çiftse 1, değilse 0 yazdır).",
                    inc + "int is_even(int n){\n  // TODO\n}\n\nint main(){\n  printf(\"%d\\n\", is_even(N));\n  return 0;\n}\n".replace("N", str(i)),
                    inc + "int is_even(int n){\n  return n%2==0;\n}\n\nint main(){\n  printf(\"%d\\n\", is_even(N));\n  return 0;\n}\n".replace("N", str(i)),
                    "1\n" if i % 2 == 0 else "0\n",
                )
            if k == 2:
                return (
                    f"{ln} • {tt} • swap #{i}",
                    "a=1, b=2 değerlerini takas edip a ve b yazdır.",
                    inc + "int main(){\n  int a=1, b=2;\n  // TODO\n  return 0;\n}\n",
                    inc + "int main(){\n  int a=1, b=2;\n  int t=a; a=b; b=t;\n  printf(\"%d %d\\n\", a, b);\n  return 0;\n}\n",
                    "2 1\n",
                )
            if k == 3:
                return (
                    f"{ln} • {tt} • max #{i}",
                    "max(a,b) fonksiyonunu yaz ve max(3,7) sonucunu yazdır.",
                    inc + "int max(int a,int b){\n  // TODO\n}\n\nint main(){\n  printf(\"%d\\n\", max(3,7));\n  return 0;\n}\n",
                    inc + "int max(int a,int b){\n  return a>b ? a : b;\n}\n\nint main(){\n  printf(\"%d\\n\", max(3,7));\n  return 0;\n}\n",
                    "7\n",
                )
            return (
                f"{ln} • {tt} • char #{i}",
                "c='A' için ASCII kodunu yazdır.",
                inc + "int main(){\n  char c='A';\n  // TODO\n  return 0;\n}\n",
                inc + "int main(){\n  char c='A';\n  printf(\"%d\\n\", (int)c);\n  return 0;\n}\n",
                "65\n",
            )

        if flags["loop"]:
            k = i % 4
            if k == 0:
                evens = [x for x in range(1, i + 1) if x % 2 == 0]
                return (
                    f"{ln} • {tt} • döngü-çift #{i}",
                    f"1..{i} arası çift sayıları yazdır.",
                    inc + "int main(){\n  // TODO\n  return 0;\n}\n",
                    inc
                    + f"int main(){{\n  for(int x=1;x<={i};x++){{\n    if(x%2==0) printf(\"%d\\n\", x);\n  }}\n  return 0;\n}}\n",
                    "".join([f"{x}\n" for x in evens]),
                )
            if k == 1:
                return (
                    f"{ln} • {tt} • faktöriyel #{i}",
                    "n=5 için faktöriyel yazdır.",
                    inc + "int main(){\n  // TODO\n  return 0;\n}\n",
                    inc + "int main(){\n  int n=5; int f=1;\n  for(int x=1;x<=n;x++) f*=x;\n  printf(\"%d\\n\", f);\n  return 0;\n}\n",
                    "120\n",
                )
            if k == 2:
                return (
                    f"{ln} • {tt} • sayaç #{i}",
                    "1..10 arasında 3'e bölünen kaç sayı var? Yazdır.",
                    inc + "int main(){\n  // TODO\n  return 0;\n}\n",
                    inc + "int main(){\n  int c=0;\n  for(int x=1;x<=10;x++) if(x%3==0) c++;\n  printf(\"%d\\n\", c);\n  return 0;\n}\n",
                    "3\n",
                )
            return (
                f"{ln} • {tt} • toplam #{i}",
                "1..10 toplamını yazdır.",
                inc + "int main(){\n  // TODO\n  return 0;\n}\n",
                inc + "int main(){\n  int s=0;\n  for(int x=1;x<=10;x++) s+=x;\n  printf(\"%d\\n\", s);\n  return 0;\n}\n",
                "55\n",
            )
        return (
            f"{ln} • {tt} • koşul #{i}",
            f"x={i} için x>5 ise buyuk, değilse kucuk yazdır.",
            inc + f"int main(){{\n  int x = {i};\n  // TODO\n  return 0;\n}}\n",
            inc
            + f"int main(){{\n  int x = {i};\n  printf(\"%s\\n\", x>5 ? \"buyuk\" : \"kucuk\");\n  return 0;\n}}\n",
            "buyuk\n" if i > 5 else "kucuk\n",
        )

    def sql_task(diff: str, i: int):
        if diff == "easy":
            return (
                f"{ln} • {tt} • SELECT #{i}",
                f"{i} değerini döndüren bir sorgu yaz.",
                "-- TODO\n",
                f"SELECT {i};\n",
                f"{i}\n",
            )
        if diff == "medium":
            return (
                f"{ln} • {tt} • WHERE #{i}",
                f"id={i} olan kaydı filtreleyen WHERE yaz (örnek).",
                "-- TODO\n",
                f"SELECT * FROM table_name WHERE id = {i};\n",
                "(filtered rows)\n",
            )
        return (
            f"{ln} • {tt} • JOIN #{i}",
            "İki tabloyu INNER JOIN ile birleştiren örnek sorgu yaz.",
            "-- TODO\n",
            "SELECT * FROM a INNER JOIN b ON a.id = b.a_id;\n",
            "(joined rows)\n",
        )

    def java_like_task(diff: str, i: int, kind: str):
        # kind: "java" | "kotlin" | "swift"
        if kind == "java":
            if diff == "easy":
                return (
                    f"{ln} • {tt} • println #{i}",
                    f"Ekrana 'Merhaba {tt} {i}' yazdır.",
                    "public class Main {\n  public static void main(String[] args) {\n    // TODO\n  }\n}\n",
                    f"public class Main {{\n  public static void main(String[] args) {{\n    System.out.println(\"Merhaba {tt} {i}\");\n  }}\n}}\n",
                    f"Merhaba {tt} {i}\n",
                )
            if diff == "medium":
                return (
                    f"{ln} • {tt} • fonksiyon #{i}",
                    "add(a,b) metodunu tamamla ve sonucu yazdır.",
                    "public class Main {\n  static int add(int a, int b) {\n    // TODO\n  }\n\n  public static void main(String[] args) {\n    System.out.println(add(A, B));\n  }\n}\n".replace(
                        "A", str(i)
                    ).replace("B", str(i + 2)),
                    f"public class Main {{\n  static int add(int a, int b) {{\n    return a + b;\n  }}\n\n  public static void main(String[] args) {{\n    System.out.println(add({i}, {i+2}));\n  }}\n}}\n",
                    f"{i + (i+2)}\n",
                )
            # hard
            if flags["loop"]:
                evens = [x for x in range(1, i + 1) if x % 2 == 0]
                return (
                    f"{ln} • {tt} • döngü #{i}",
                    f"1..{i} arası çift sayıları yazdır.",
                    "public class Main {\n  public static void main(String[] args) {\n    // TODO\n  }\n}\n",
                    "public class Main {\n  public static void main(String[] args) {\n    for (int x=1; x<=N; x++) {\n      if (x % 2 == 0) System.out.println(x);\n    }\n  }\n}\n".replace(
                        "N", str(i)
                    ),
                    "".join([f"{x}\n" for x in evens]),
                )
            return (
                f"{ln} • {tt} • koşul #{i}",
                f"x={i} için x>5 ise buyuk değilse kucuk yazdır.",
                "public class Main {\n  public static void main(String[] args) {\n    int x = X;\n    // TODO\n  }\n}\n".replace(
                    "X", str(i)
                ),
                "public class Main {\n  public static void main(String[] args) {\n    int x = X;\n    System.out.println(x > 5 ? \"buyuk\" : \"kucuk\");\n  }\n}\n".replace(
                    "X", str(i)
                ),
                "buyuk\n" if i > 5 else "kucuk\n",
            )

        if kind == "kotlin":
            if diff == "easy":
                return (
                    f"{ln} • {tt} • println #{i}",
                    f"Ekrana \"Merhaba {tt} {i}\" yazdır.",
                    "fun main() {\n  // TODO\n}\n",
                    f"fun main() {{\n  println(\"Merhaba {tt} {i}\")\n}}\n",
                    f"Merhaba {tt} {i}\n",
                )
            if diff == "medium":
                return (
                    f"{ln} • {tt} • fonksiyon #{i}",
                    "add(a,b) fonksiyonunu tamamla ve sonucu yazdır.",
                    "fun add(a:Int, b:Int):Int {\n  // TODO\n}\n\nfun main() {\n  println(add(A, B))\n}\n".replace(
                        "A", str(i)
                    ).replace("B", str(i + 2)),
                    f"fun add(a:Int, b:Int):Int {{\n  return a + b\n}}\n\nfun main() {{\n  println(add({i}, {i+2}))\n}}\n",
                    f"{i + (i+2)}\n",
                )
            if flags["loop"]:
                evens = [x for x in range(1, i + 1) if x % 2 == 0]
                return (
                    f"{ln} • {tt} • döngü #{i}",
                    f"1..{i} arası çift sayıları yazdır.",
                    "fun main() {\n  // TODO\n}\n",
                    "fun main() {\n  for (x in 1..N) {\n    if (x % 2 == 0) println(x)\n  }\n}\n".replace(
                        "N", str(i)
                    ),
                    "".join([f"{x}\n" for x in evens]),
                )
            return (
                f"{ln} • {tt} • koşul #{i}",
                f"x={i} için x>5 ise buyuk değilse kucuk yazdır.",
                "fun main() {\n  val x = X\n  // TODO\n}\n".replace("X", str(i)),
                "fun main() {\n  val x = X\n  println(if (x > 5) \"buyuk\" else \"kucuk\")\n}\n".replace(
                    "X", str(i)
                ),
                "buyuk\n" if i > 5 else "kucuk\n",
            )

        if kind == "swift":
            if diff == "easy":
                return (
                    f"{ln} • {tt} • print #{i}",
                    f"Ekrana \"Merhaba {tt} {i}\" yazdır.",
                    "// TODO\n",
                    f"print(\"Merhaba {tt} {i}\")\n",
                    f"Merhaba {tt} {i}\n",
                )
            if diff == "medium":
                return (
                    f"{ln} • {tt} • fonksiyon #{i}",
                    "add(a,b) fonksiyonunu tamamla ve sonucu yazdır.",
                    "func add(_ a:Int, _ b:Int) -> Int {\n  // TODO\n}\nprint(add(A, B))\n".replace(
                        "A", str(i)
                    ).replace("B", str(i + 2)),
                    f"func add(_ a:Int, _ b:Int) -> Int {{\n  return a + b\n}}\nprint(add({i}, {i+2}))\n",
                    f"{i + (i+2)}\n",
                )
            if flags["loop"]:
                evens = [x for x in range(1, i + 1) if x % 2 == 0]
                return (
                    f"{ln} • {tt} • döngü #{i}",
                    f"1...{i} arası çift sayıları yazdır.",
                    "// TODO\n",
                    "for x in 1...N {\n  if x % 2 == 0 { print(x) }\n}\n".replace(
                        "N", str(i)
                    ),
                    "".join([f"{x}\n" for x in evens]),
                )
            return (
                f"{ln} • {tt} • koşul #{i}",
                f"x={i} için x>5 ise buyuk değilse kucuk yazdır.",
                "let x = X\n// TODO\n".replace("X", str(i)),
                "let x = X\nprint(x > 5 ? \"buyuk\" : \"kucuk\")\n".replace("X", str(i)),
                "buyuk\n" if i > 5 else "kucuk\n",
            )

    def go_task(diff: str, i: int):
        if diff == "easy":
            return (
                f"{ln} • {tt} • fmt.Println #{i}",
                f"Ekrana \"Merhaba {tt} {i}\" yazdır.",
                "package main\n\nimport \"fmt\"\n\nfunc main() {\n  // TODO\n}\n",
                f"package main\n\nimport \"fmt\"\n\nfunc main() {{\n  fmt.Println(\"Merhaba {tt} {i}\")\n}}\n",
                f"Merhaba {tt} {i}\n",
            )
        if diff == "medium":
            return (
                f"{ln} • {tt} • fonksiyon #{i}",
                "add(a,b) fonksiyonunu tamamla ve sonucu yazdır.",
                "package main\n\nimport \"fmt\"\n\nfunc add(a int, b int) int {\n  // TODO\n}\n\nfunc main() {\n  fmt.Println(add(A, B))\n}\n".replace(
                    "A", str(i)
                ).replace("B", str(i + 2)),
                f"package main\n\nimport \"fmt\"\n\nfunc add(a int, b int) int {{\n  return a + b\n}}\n\nfunc main() {{\n  fmt.Println(add({i}, {i+2}))\n}}\n",
                f"{i + (i+2)}\n",
            )
        if flags["loop"]:
            evens = [x for x in range(1, i + 1) if x % 2 == 0]
            return (
                f"{ln} • {tt} • döngü #{i}",
                f"1..{i} arası çift sayıları yazdır.",
                "package main\n\nimport \"fmt\"\n\nfunc main() {\n  // TODO\n}\n",
                "package main\n\nimport \"fmt\"\n\nfunc main() {\n  for x := 1; x <= N; x++ {\n    if x%2==0 { fmt.Println(x) }\n  }\n}\n".replace(
                    "N", str(i)
                ),
                "".join([f"{x}\n" for x in evens]),
            )
        return (
            f"{ln} • {tt} • koşul #{i}",
            f"x={i} için x>5 ise buyuk değilse kucuk yazdır.",
            "package main\n\nimport \"fmt\"\n\nfunc main() {\n  x := X\n  // TODO\n}\n".replace(
                "X", str(i)
            ),
            "package main\n\nimport \"fmt\"\n\nfunc main() {\n  x := X\n  if x > 5 { fmt.Println(\"buyuk\") } else { fmt.Println(\"kucuk\") }\n}\n".replace(
                "X", str(i)
            ),
            "buyuk\n" if i > 5 else "kucuk\n",
        )

    def rust_task(diff: str, i: int):
        if diff == "easy":
            return (
                f"{ln} • {tt} • println #{i}",
                f"Ekrana \"Merhaba {tt} {i}\" yazdır.",
                "fn main() {\n  // TODO\n}\n",
                f"fn main() {{\n  println!(\"Merhaba {tt} {i}\");\n}}\n",
                f"Merhaba {tt} {i}\n",
            )
        if diff == "medium":
            return (
                f"{ln} • {tt} • fonksiyon #{i}",
                "add(a,b) fonksiyonunu tamamla ve sonucu yazdır.",
                "fn add(a:i32, b:i32) -> i32 {\n  // TODO\n}\n\nfn main(){\n  println!(\"{}\", add(A, B));\n}\n".replace(
                    "A", str(i)
                ).replace("B", str(i + 2)),
                f"fn add(a:i32, b:i32) -> i32 {{\n  a + b\n}}\n\nfn main(){{\n  println!(\"{{}}\", add({i}, {i+2}));\n}}\n",
                f"{i + (i+2)}\n",
            )
        if flags["loop"]:
            evens = [x for x in range(1, i + 1) if x % 2 == 0]
            return (
                f"{ln} • {tt} • döngü #{i}",
                f"1..={i} arası çift sayıları yazdır.",
                "fn main(){\n  // TODO\n}\n",
                "fn main(){\n  for x in 1..=N {\n    if x % 2 == 0 { println!(\"{}\", x); }\n  }\n}\n".replace(
                    "N", str(i)
                ),
                "".join([f"{x}\n" for x in evens]),
            )
        return (
            f"{ln} • {tt} • koşul #{i}",
            f"x={i} için x>5 ise buyuk değilse kucuk yazdır.",
            "fn main(){\n  let x = X;\n  // TODO\n}\n".replace("X", str(i)),
            "fn main(){\n  let x = X;\n  if x > 5 { println!(\"buyuk\"); } else { println!(\"kucuk\"); }\n}\n".replace(
                "X", str(i)
            ),
            "buyuk\n" if i > 5 else "kucuk\n",
        )

    def php_task(diff: str, i: int):
        if diff == "easy":
            return (
                f"{ln} • {tt} • echo #{i}",
                f"Ekrana \"Merhaba {tt} {i}\" yazdır.",
                "<?php\n// TODO\n",
                f"<?php\necho \"Merhaba {tt} {i}\\n\";\n",
                f"Merhaba {tt} {i}\n",
            )
        if diff == "medium":
            return (
                f"{ln} • {tt} • fonksiyon #{i}",
                "add(a,b) fonksiyonunu tamamla ve sonucu yazdır.",
                "<?php\nfunction add($a, $b) {\n  // TODO\n}\necho add(A, B) . \"\\n\";\n".replace(
                    "A", str(i)
                ).replace("B", str(i + 2)),
                f"<?php\nfunction add($a, $b) {{\n  return $a + $b;\n}}\necho add({i}, {i+2}) . \"\\n\";\n",
                f"{i + (i+2)}\n",
            )
        return (
            f"{ln} • {tt} • koşul #{i}",
            f"x={i} için x>5 ise buyuk değilse kucuk yazdır.",
            "<?php\n$x = X;\n// TODO\n".replace("X", str(i)),
            "<?php\n$x = X;\necho ($x > 5 ? \"buyuk\" : \"kucuk\") . \"\\n\";\n".replace("X", str(i)),
            "buyuk\n" if i > 5 else "kucuk\n",
        )

    def ruby_task(diff: str, i: int):
        if diff == "easy":
            return (
                f"{ln} • {tt} • puts #{i}",
                f"Ekrana \"Merhaba {tt} {i}\" yazdır.",
                "# TODO\n",
                f"puts \"Merhaba {tt} {i}\"\n",
                f"Merhaba {tt} {i}\n",
            )
        if diff == "medium":
            return (
                f"{ln} • {tt} • fonksiyon #{i}",
                "add(a,b) metodunu tamamla ve sonucu yazdır.",
                "def add(a, b)\n  # TODO\nend\nputs add(A, B)\n".replace("A", str(i)).replace(
                    "B", str(i + 2)
                ),
                f"def add(a, b)\n  a + b\nend\nputs add({i}, {i+2})\n",
                f"{i + (i+2)}\n",
            )
        return (
            f"{ln} • {tt} • koşul #{i}",
            f"x={i} için x>5 ise buyuk değilse kucuk yazdır.",
            "x = X\n# TODO\n".replace("X", str(i)),
            "x = X\nputs(x > 5 ? 'buyuk' : 'kucuk')\n".replace("X", str(i)),
            "buyuk\n" if i > 5 else "kucuk\n",
        )

    def r_task(diff: str, i: int):
        if diff == "easy":
            return (
                f"{ln} • {tt} • cat #{i}",
                f"Ekrana 'Merhaba {tt} {i}' yazdır.",
                "# TODO\n",
                f"cat('Merhaba {tt} {i}\\n')\n",
                f"Merhaba {tt} {i}\n",
            )
        if diff == "medium":
            return (
                f"{ln} • {tt} • toplama #{i}",
                f"{i}+{i+2} sonucunu yazdır.",
                "a <- A\nb <- B\n# TODO\n".replace("A", str(i)).replace("B", str(i + 2)),
                f"a <- {i}\nb <- {i+2}\ncat(a + b, \"\\n\")\n",
                f"{i + (i+2)} \n",
            )
        return (
            f"{ln} • {tt} • koşul #{i}",
            f"x={i} için x>5 ise buyuk değilse kucuk yazdır.",
            "x <- X\n# TODO\n".replace("X", str(i)),
            "x <- X\nif (x > 5) { cat('buyuk\\n') } else { cat('kucuk\\n') }\n".replace("X", str(i)),
            "buyuk\n" if i > 5 else "kucuk\n",
        )

    def matlab_task(diff: str, i: int):
        if diff == "easy":
            return (
                f"{ln} • {tt} • disp #{i}",
                f"Ekrana 'Merhaba {tt} {i}' yazdır.",
                "% TODO\n",
                f"disp('Merhaba {tt} {i}')\n",
                f"Merhaba {tt} {i}\n",
            )
        if diff == "medium":
            return (
                f"{ln} • {tt} • toplama #{i}",
                f"{i}+{i+2} sonucunu yazdır.",
                "a = A;\nb = B;\n% TODO\n".replace("A", str(i)).replace("B", str(i + 2)),
                f"a = {i};\nb = {i+2};\ndisp(a + b)\n",
                f"{i + (i+2)}\n",
            )
        return (
            f"{ln} • {tt} • koşul #{i}",
            f"x={i} için x>5 ise buyuk değilse kucuk yazdır.",
            "x = X;\n% TODO\n".replace("X", str(i)),
            "x = X;\nif x > 5\n  disp('buyuk')\nelse\n  disp('kucuk')\nend\n".replace("X", str(i)),
            "buyuk\n" if i > 5 else "kucuk\n",
        )

    def cpp_task(diff: str, i: int):
        inc = "#include <iostream>\n\n"
        if diff == "easy":
            return (
                f"{ln} • {tt} • cout #{i}",
                f"cout ile 'Merhaba {tt} {i}' yazdır.",
                inc + "int main() {\n  // TODO\n  return 0;\n}\n",
                inc + f"int main() {{\n  std::cout << \"Merhaba {tt} {i}\" << std::endl;\n  return 0;\n}}\n",
                f"Merhaba {tt} {i}\n",
            )
        if diff == "medium":
            return (
                f"{ln} • {tt} • fonksiyon #{i}",
                "add(a,b) fonksiyonunu tamamla ve sonucu yazdır.",
                inc
                + "int add(int a, int b){\n  // TODO\n}\n\nint main(){\n  std::cout << add(A, B) << std::endl;\n  return 0;\n}\n".replace(
                    "A", str(i)
                ).replace("B", str(i + 2)),
                inc
                + f"int add(int a, int b){{\n  return a + b;\n}}\n\nint main(){{\n  std::cout << add({i}, {i+2}) << std::endl;\n  return 0;\n}}\n",
                f"{i + (i+2)}\n",
            )
        if flags["loop"]:
            evens = [x for x in range(1, i + 1) if x % 2 == 0]
            return (
                f"{ln} • {tt} • döngü #{i}",
                f"1..{i} arası çift sayıları yazdır.",
                inc + "int main(){\n  // TODO\n  return 0;\n}\n",
                inc
                + f"int main(){{\n  for(int x=1;x<={i};x++){{\n    if(x%2==0) std::cout << x << std::endl;\n  }}\n  return 0;\n}}\n",
                "".join([f"{x}\n" for x in evens]),
            )
        return (
            f"{ln} • {tt} • koşul #{i}",
            f"x={i} için x>5 ise buyuk değilse kucuk yazdır.",
            inc + f"int main(){{\n  int x = {i};\n  // TODO\n  return 0;\n}}\n",
            inc
            + f"int main(){{\n  int x = {i};\n  std::cout << (x>5 ? \"buyuk\" : \"kucuk\") << std::endl;\n  return 0;\n}}\n",
            "buyuk\n" if i > 5 else "kucuk\n",
        )

    def generic_task(diff: str, i: int):
        # For languages we don't fully template yet, still provide meaningful pseudo-template text
        # but with real expected output and structured steps.
        if diff == "easy":
            k = i % 5
            if k == 0:
                return (
                    f"{ln} • {tt} • çıktı #{i}",
                    f"Bu dilde ekrana 'OK{i}' yazdır (kendi sözdizimine göre).",
                    "// TODO: bu dilin sözdizimiyle yaz\n",
                    "// Çözüm: kendi diline göre yaz\n",
                    f"OK{i}\n",
                )
            if k == 1:
                return (
                    f"{ln} • {tt} • değişken #{i}",
                    "x=10, y=3 tanımla ve x*y yazdır.",
                    "// TODO\n",
                    "// TODO\n",
                    "30\n",
                )
            if k == 2:
                return (
                    f"{ln} • {tt} • string #{i}",
                    "name='Ada' için 'Merhaba Ada' yazdır (birleştirme).",
                    "// TODO\n",
                    "// TODO\n",
                    "Merhaba Ada\n",
                )
            if k == 3:
                return (
                    f"{ln} • {tt} • format #{i}",
                    "a=2, b=5 için '2+5=7' formatında yazdır.",
                    "// TODO\n",
                    "// TODO\n",
                    "2+5=7\n",
                )
            return (
                f"{ln} • {tt} • uzunluk #{i}",
                "3 elemanlı bir liste/dizi tanımla ve uzunluğunu yazdır.",
                "// TODO\n",
                "// TODO\n",
                "3\n",
            )
        if diff == "medium":
            k = i % 5
            if k == 0:
                return (
                    f"{ln} • {tt} • toplama #{i}",
                    f"{i}+{i+2} sonucunu yazdır.",
                    "// TODO\n",
                    "// TODO\n",
                    f"{i + (i+2)}\n",
                )
            if k == 1:
                return (
                    f"{ln} • {tt} • fonksiyon #{i}",
                    "add(a,b) fonksiyonu/metodu yaz ve add(3,7) yazdır.",
                    "// TODO\n",
                    "// TODO\n",
                    "10\n",
                )
            if k == 2:
                return (
                    f"{ln} • {tt} • koşul #{i}",
                    "x=4 için x çift mi? 'true/false' yazdır.",
                    "// TODO\n",
                    "// TODO\n",
                    "true\n",
                )
            if k == 3:
                return (
                    f"{ln} • {tt} • toplam #{i}",
                    "1..10 toplamını yazdır.",
                    "// TODO\n",
                    "// TODO\n",
                    "55\n",
                )
            return (
                f"{ln} • {tt} • string-len #{i}",
                "s='hello' için uzunluğu yazdır.",
                "// TODO\n",
                "// TODO\n",
                "5\n",
            )
        k = i % 4
        if k == 0:
            return (
                f"{ln} • {tt} • döngü #{i}",
                f"1..{i} arasında kaç tane sayı 3'e bölünür? Yazdır.",
                "// TODO\n",
                "// TODO\n",
                str(len([x for x in range(1, i + 1) if x % 3 == 0])) + "\n",
            )
        if k == 1:
            return (
                f"{ln} • {tt} • filtre #{i}",
                "nums=[1,2,3,4,5] içinden tekleri yazdır (liste/dizi).",
                "// TODO\n",
                "// TODO\n",
                "1,3,5\n",
            )
        if k == 2:
            return (
                f"{ln} • {tt} • string-rev #{i}",
                "s='abcd' stringini ters çevirip yazdır.",
                "// TODO\n",
                "// TODO\n",
                "dcba\n",
            )
        return (
            f"{ln} • {tt} • koşul #{i}",
            f"x={i} için x>5 ise 'buyuk' yazdır.",
            "// TODO\n",
            "// TODO\n",
            "buyuk\n" if i > 5 else "",
        )

    def pick_task(diff: str, i: int):
        if lid == "python":
            return python_task(diff, i)
        if lid in ("javascript", "typescript"):
            return js_task(diff, i)
        if lid == "dart":
            return dart_task(diff, i)
        if lid == "c":
            return c_task(diff, i)
        if lid == "cpp":
            return cpp_task(diff, i)
        if lid == "sql":
            return sql_task(diff, i)
        if lid == "java":
            return java_like_task(diff, i, "java")
        if lid == "kotlin":
            return java_like_task(diff, i, "kotlin")
        if lid == "swift":
            return java_like_task(diff, i, "swift")
        if lid == "go":
            return go_task(diff, i)
        if lid == "rust":
            return rust_task(diff, i)
        if lid == "php":
            return php_task(diff, i)
        if lid == "ruby":
            return ruby_task(diff, i)
        if lid == "r":
            return r_task(diff, i)
        if lid == "matlab":
            return matlab_task(diff, i)
        return generic_task(diff, i)

    # Prefer curated banks where available; fallback to parametric generator otherwise.
    if lid == "python":
        return python_curated()
    if lid in ("javascript", "typescript"):
        return js_curated()
    if lid == "dart":
        return dart_curated()

    # Fallback: generate a smaller, more usable set (12 total) and dedupe.
    out: list[dict] = []
    idx = 1
    for diff in ("easy", "medium", "hard"):
        for i in range(1, 5):
            title, prompt, starter, solution, exp = pick_task(diff, i * 3 + 1)
            out.append(pack(diff, idx, title, prompt, starter, solution, exp))
            idx += 1
    return _dedupe(out)


def main():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    path = os.path.join(root, "assets", "content", "catalog.json")
    with open(path, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    removed_dups = dedupe_topics(catalog)
    added_topics = ensure_curriculum(catalog)
    sorted_langs = sort_topics_by_curriculum(catalog)

    # Bump version so Flutter rebuilds pick it up and repository can detect changes.
    # Use epoch seconds (int) to guarantee change across runs.
    catalog["version"] = int(time.time())

    touched = 0
    global_seen_prompts: set[str] = set()  # legacy; not used in fixed-size banks
    for lang in catalog.get("languages", []):
        lang_id = (lang.get("id", "") or "").strip()
        lang_name = lang.get("name", "").strip() or lang.get("id", "")
        for topic in lang.get("topics", []):
            questions = topic.get("questions") or []
            topic["questions"] = questions
            # Ensure compiler challenges exist per topic (easy/medium/hard)
            ccs = topic.get("compilerChallenges") or []
            topic["compilerChallenges"] = ccs
            # Ensure library questions exist per topic (easy/medium/hard)
            lqs = topic.get("libraryQuestions") or []
            topic["libraryQuestions"] = lqs

            topic_title = topic.get("title", "").strip() or topic.get("id", "")
            md = topic.get("contentMarkdown", "") or ""

            # Expand teaching content if placeholder/too short
            md_lower = md.lower()
            is_placeholder = ("baslangic sayfasidir" in md_lower) or ("icerigi genisletmek" in md_lower) or (len(md.strip()) < 220)
            # Re-generate previously auto-generated teaching notes too
            is_auto_teaching = ("yazılı şekilde öğretir" in md_lower) and ("videoyu izleyemeyen" in md_lower)
            if is_placeholder or is_auto_teaching:
                topic_id = topic.get("id", "").strip() or slugify(topic_title)
                topic["contentMarkdown"] = make_teaching_markdown(
                    lang_id=lang_id,
                    lang_name=lang_name,
                    topic_title=topic_title,
                    topic_id=topic_id,
                    md=md,
                )

            # Keep manual questions; regenerate auto-* questions to make them smarter.
            manual_questions = [q for q in questions if isinstance(q, dict) and not str(q.get("id", "")).startswith("auto-")]
            auto_questions = [q for q in questions if isinstance(q, dict) and str(q.get("id", "")).startswith("auto-")]
            if auto_questions:
                topic["questions"] = manual_questions
                questions = topic["questions"]

            # Seed global de-dupe with existing manual prompts (so autos won't repeat them).
            for q in manual_questions:
                if isinstance(q, dict):
                    global_seen_prompts.add(norm_prompt(q.get("prompt", "")))

            existing_ids = {q.get("id", "") for q in questions if isinstance(q, dict)}
            existing_ids.discard("")

            # Expand quiz bank up to 20, with easy/medium/hard distribution.
            # Target: 20 questions per difficulty (60 total) per topic.
            if len(questions) < 60:
                need = 60 - len(questions)
                topic_id = topic.get("id", "").strip() or slugify(topic_title)
                extra = make_generic_questions(
                    lang_id,
                    lang_name,
                    topic_id,
                    topic_title,
                    md,
                    need,
                    existing_ids,
                    global_seen_prompts,
                )
                # Ensure per-difficulty caps after merge:
                merged = (topic["questions"] or []) + (extra or [])
                by = {"easy": [], "medium": [], "hard": []}
                manual = [q for q in merged if isinstance(q, dict) and not str(q.get("id", "")).startswith("auto-")]
                auto = [q for q in merged if isinstance(q, dict) and str(q.get("id", "")).startswith("auto-")]
                # Keep manual first, then auto, but enforce 20 per diff total.
                out_final: list[dict] = []
                for diff in ("easy", "medium", "hard"):
                    take: list[dict] = []
                    take += [q for q in manual if (q.get("difficulty") == diff)]
                    take += [q for q in auto if (q.get("difficulty") == diff)]
                    take = take[:20]
                    out_final.extend(take)
                topic["questions"] = out_final
                touched += 1

            # Target: 20 library questions per difficulty (60 total) per topic.
            # Keep manual first, then generated lib-* questions.
            # If there are old auto-generated lib-* questions, drop them and regenerate.
            existing_lq0 = topic.get("libraryQuestions") or []
            manual_only_lq0 = [
                q
                for q in existing_lq0
                if isinstance(q, dict) and not str(q.get("id", "")).startswith("lib-")
            ]
            if any(
                isinstance(q, dict) and str(q.get("id", "")).startswith("lib-")
                for q in existing_lq0
            ):
                topic["libraryQuestions"] = manual_only_lq0

            if len(topic.get("libraryQuestions") or []) < 60:
                topic_id = topic.get("id", "").strip() or slugify(topic_title)

                # Use a shared id pool so we never collide.
                all_existing_ids: set[str] = set()
                for l2 in catalog.get("languages", []):
                    for t2 in (l2.get("topics") or []):
                        for q in (t2.get("questions") or []):
                            if isinstance(q, dict) and q.get("id"):
                                all_existing_ids.add(str(q.get("id")))
                        for q in (t2.get("libraryQuestions") or []):
                            if isinstance(q, dict) and q.get("id"):
                                all_existing_ids.add(str(q.get("id")))
                        for q in (t2.get("compilerChallenges") or []):
                            if isinstance(q, dict) and q.get("id"):
                                all_existing_ids.add(str(q.get("id")))

                lib_generated = make_generic_questions(
                    lang_id,
                    lang_name,
                    topic_id,
                    topic_title,
                    md,
                    60,
                    all_existing_ids,
                    global_seen_prompts,
                )

                # Retag as library questions (unique ids, visible prefix).
                for q in lib_generated:
                    if not isinstance(q, dict):
                        continue
                    q["id"] = next_id(
                        all_existing_ids,
                        f"lib-{slugify(lang_name)}-{slugify(topic_title)}-q",
                    )
                    q["prompt"] = "[Kütüphane] " + str(q.get("prompt", ""))

                merged_lq = (topic.get("libraryQuestions") or []) + (lib_generated or [])
                manual_lq = [
                    q
                    for q in merged_lq
                    if isinstance(q, dict) and not str(q.get("id", "")).startswith("lib-")
                ]
                auto_lq = [
                    q
                    for q in merged_lq
                    if isinstance(q, dict) and str(q.get("id", "")).startswith("lib-")
                ]

                out_lq_final: list[dict] = []
                for diff in ("easy", "medium", "hard"):
                    take: list[dict] = []
                    take += [q for q in manual_lq if (q.get("difficulty") == diff)]
                    take += [q for q in auto_lq if (q.get("difficulty") == diff)]
                    take = take[:20]
                    out_lq_final.extend(take)
                topic["libraryQuestions"] = out_lq_final
                touched += 1

            # Target: 20 compiler challenges per difficulty (60 total) per topic.
            # Always ensure the count and per-difficulty split (manual items are preserved first).
            topic_id = topic.get("id", "").strip() or slugify(topic_title)
            generated_ccs = make_compiler_challenges(
                lang_id=lang_id,
                lang_name=lang_name,
                topic_id=topic_id,
                topic_title=topic_title,
                md=md,
            )
            existing_ccs = (ccs or [])
            manual_cc = [
                q
                for q in existing_ccs
                if isinstance(q, dict) and not str(q.get("id", "")).startswith("cc-")
            ]
            existing_auto_cc = [
                q
                for q in existing_ccs
                if isinstance(q, dict) and str(q.get("id", "")).startswith("cc-")
            ]
            # Prefer newly generated auto challenges over older auto challenges
            auto_cc = (generated_ccs or []) + existing_auto_cc
            out_cc_final: list[dict] = []
            for diff in ("easy", "medium", "hard"):
                take: list[dict] = []
                take += [q for q in manual_cc if (q.get("difficulty") == diff)]
                take += [q for q in auto_cc if (q.get("difficulty") == diff)]
                take = take[:20]
                out_cc_final.extend(take)
            topic["compilerChallenges"] = out_cc_final

    # Pretty print, keep Unicode
    out = json.dumps(catalog, ensure_ascii=False, indent=2)
    out += "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)

    print(
        f"[{datetime.now().isoformat(timespec='seconds')}] topics_added={added_topics} topics_sorted={sorted_langs} "
        f"topics_extended={touched} topics_deduped={removed_dups}"
    )


if __name__ == "__main__":
    main()

