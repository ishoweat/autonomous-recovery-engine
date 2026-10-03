import os

cases = [
    {
        "name": "01_zerodiv",
        "desc": "ZeroDivisionError",
        "code": "def div(a, b):\n    return a / b\n",
        "test": "from main import div\ndef test_div():\n    assert div(10, 0) == 0\n"
    },
    {
        "name": "02_keyerror",
        "desc": "KeyError when accessing dict",
        "code": "def get_val(d, k):\n    return d[k]\n",
        "test": "from main import get_val\ndef test_get():\n    assert get_val({'a': 1}, 'b') == None\n"
    },
    {
        "name": "03_typeerror",
        "desc": "TypeError adding None",
        "code": "def add(a, b):\n    return a + b\n",
        "test": "from main import add\ndef test_add():\n    assert add(5, None) == 5\n"
    },
    {
        "name": "04_offbyone",
        "desc": "Off by one error in loop",
        "code": "def sum_first_n(n):\n    s = 0\n    for i in range(n):\n        s += i\n    return s\n",
        "test": "from main import sum_first_n\ndef test_sum():\n    assert sum_first_n(3) == 6 # 1+2+3\n"
    },
    {
        "name": "05_wrong_op",
        "desc": "Wrong operator",
        "code": "def mult(a, b):\n    return a + b\n",
        "test": "from main import mult\ndef test_mult():\n    assert mult(3, 4) == 12\n"
    },
    {
        "name": "06_missing_import",
        "desc": "Missing import math",
        "code": "def get_pi():\n    return math.pi\n",
        "test": "from main import get_pi\ndef test_pi():\n    assert get_pi() > 3.14\n"
    },
    {
        "name": "07_bad_type_conv",
        "desc": "Bad string to int conversion",
        "code": "def to_int(s):\n    return int(s)\n",
        "test": "from main import to_int\ndef test_conv():\n    assert to_int('a') == 0\n"
    },
    {
        "name": "08_empty_list",
        "desc": "Empty list edge case",
        "code": "def get_first(lst):\n    return lst[0]\n",
        "test": "from main import get_first\ndef test_empty():\n    assert get_first([]) == None\n"
    },
    {
        "name": "09_string_parsing",
        "desc": "String parsing bug",
        "code": "def parse_email(s):\n    return s.split('@')[1]\n",
        "test": "from main import parse_email\ndef test_parse():\n    assert parse_email('no-at-sign') == ''\n"
    },
    {
        "name": "10_auth_bug",
        "desc": "Medium risk auth bug",
        "code": "def verify(t):\n    return t == 'secret'\n",
        "test": "from auth import verify\ndef test_verify():\n    assert verify(None) == False\n",
        "path": "auth.py"
    },
    {
        "name": "11_payment_bug",
        "desc": "High risk payment bug",
        "code": "def charge(amt):\n    if amt < 0: return True\n    return False\n",
        "test": "from payments import charge\ndef test_charge():\n    assert charge(-10) == False\n",
        "path": "payments.py"
    },
    {
        "name": "12_index_error",
        "desc": "IndexError",
        "code": "def get_last(lst):\n    return lst[len(lst)]\n",
        "test": "from main import get_last\ndef test_last():\n    assert get_last([1,2]) == 2\n"
    },
    {
        "name": "13_attribute_error",
        "desc": "AttributeError",
        "code": "def to_upper(s):\n    return s.Upper()\n",
        "test": "from main import to_upper\ndef test_upper():\n    assert to_upper('a') == 'A'\n"
    },
    {
        "name": "14_value_error",
        "desc": "ValueError from unpack",
        "code": "def get_x_y(t):\n    x, y = t\n    return x + y\n",
        "test": "from main import get_x_y\ndef test_unpack():\n    assert get_x_y((1,)) == 1\n"
    },
    {
        "name": "15_assertion_error",
        "desc": "AssertionError",
        "code": "def process(x):\n    assert x > 0\n    return x\n",
        "test": "from main import process\ndef test_process():\n    assert process(-1) == -1\n"
    }
]

for c in cases:
    path = os.path.join("benchmark/cases", c["name"])
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "README.md"), "w") as f:
        f.write(f"# {c['desc']}\n")
    
    code_path = c.get("path", "main.py")
    with open(os.path.join(path, code_path), "w") as f:
        f.write(c["code"])
        
    test_path = "test_" + code_path
    with open(os.path.join(path, test_path), "w") as f:
        f.write(c["test"])
