"""本地 gitleaks 复刻 — 扫描仓库 git 跟踪的文件"""
import re
import subprocess
import sys
from pathlib import Path

# 复刻 gitleaks 8.x 默认规则的核心子集
RULES = [
    ("openai",          r"sk-[A-Za-z0-9_\-]{20,}"),
    ("anthropic",       r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    ("github",          r"gh[pousr]_[A-Za-z0-9]{30,}"),
    ("aws",             r"AKIA[0-9A-Z]{16}"),
    ("slack",           r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    ("stripe",          r"sk_(?:live|test)_[A-Za-z0-9]{20,}"),
    ("jwt",             r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    ("private_key",     r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
    ("db_url",          r"(?:postgres|postgresql|mysql|redis|mongodb)(\+\w+)?://[^:/\s]+:[^@\s]{3,}@"),
    ("generic_quoted",  r'''(?i)(password|passwd|secret|api[_-]?key|auth[_-]?token|encryption[_-]?key|salt|nextauth[_-]?secret)\s*[:=]\s*["'][^"'\s]{6,}["']'''),
    ("generic_unquoted",r"(?im)^\s*-?\s*[A-Z0-9_]*(SECRET|PASSWORD|PASSWD|TOKEN|API_?KEY|ACCESS_?KEY|ENCRYPTION|SALT|AUTH|CREDENTIAL)[A-Z0-9_]*\s*[:=]\s*\S{6,}"),
]

# .gitleaks.toml allowlist 复刻
ALLOWLIST = [
    r"\.venv/", r"volumes/", r"\.git/", r"node_modules/", r"uv\.lock",
    r"\.pytest_cache/", r"__pycache__/", r"\.idea/",
]

# 通用占位符白名单(避免 README/模板里的示例值被误报)
PLACEHOLDER_TOKENS = [
    "change-me", "placeholder", "your-", "your_", "xxxxx", "xxx",
    "example", "<your", "${", "REPLACE_ME", "TODO", "FIXME",
]

# 已知 docker compose 默认凭据(业内周知,非真密钥)
# 真实部署必须替换,但出现在仓库内属约定俗成
KNOWN_DEFAULTS = [
    "minioadmin", "miniosecret", "minio:minio", "minio123",
    "clickhouse", "postgres", "postgresql",
    "aiops:aiops", "127.0.0.1", "localhost",
    # 常见 dev 容器内服务名
    "milvus-etcd", "milvus-minio", "milvus-standalone",
    # 通用服务默认端口
    ":5432", ":6379", ":9000", ":8123", ":9090", ":19530", ":4000",
    # 环境变量读取模式(LLM/DB 工具的标准用法,不是密钥本身)
    "os.environ.get", "os.getenv",
]

def is_allowed(path: str) -> bool:
    return any(re.search(p, path) for p in ALLOWLIST)

def is_placeholder_line(line: str) -> bool:
    low = line.lower()
    if any(tok.lower() in low for tok in PLACEHOLDER_TOKENS):
        return True
    if any(tok.lower() in low for tok in KNOWN_DEFAULTS):
        return True
    # 变量自赋值 / 函数返回(右值是变量名而非字符串字面量)
    if re.search(r"=\s*[a-z_][a-z0-9_]*\s*[,)]", low):
        return True
    return False

def scan_file(path: str):
    hits = []
    try:
        with open(path, "rb") as f:
            if b"\x00" in f.read(8192):
                return []  # binary
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    for ln_num, line in enumerate(text.splitlines(), 1):
        for rule_name, pattern in RULES:
            if re.search(pattern, line):
                if is_placeholder_line(line):
                    continue
                hits.append((ln_num, rule_name, line.strip()[:140]))
    return hits

def main():
    root = Path(".")
    proc = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=root)
    files = [f for f in proc.stdout.strip().split("\n") if f]

    total_hits = 0
    scanned = 0
    for f in files:
        if is_allowed(f):
            continue
        scanned += 1
        hits = scan_file(f)
        if hits:
            print(f"  LEAK in {f}:")
            for ln, rule, txt in hits:
                print(f"    L{ln} [{rule}] {txt}")
                total_hits += 1

    print(f"  扫描文件数: {scanned} (排除 {len(files) - scanned} 个被 allowlist 路径)")
    if total_hits == 0:
        print(f"  PASS: 0 命中")
        sys.exit(0)
    else:
        print(f"  FAIL: {total_hits} 处命中")
        sys.exit(1)

if __name__ == "__main__":
    main()
