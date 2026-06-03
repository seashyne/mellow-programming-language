# tests/test_v148.py — MellowLang v1.4.8 comprehensive test suite
# Covers: get/call module system, AI engine, C VM fallback, all syntax
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from mellowlang.compiler import Compiler
from mellowlang.vm.vm import MellowVM, RunConfig
from mellowlang.compiler.legacy import Compiler as LegacyCompiler
from mellowlang.vm.cbridge import run_bytecode, c_vm_available

# ── helpers ──────────────────────────────────────────────────────────────────

def run(src, **kw):
    c = Compiler(); vm = MellowVM()
    prog = c.compile(src)
    vm.run(prog, config=RunConfig(**kw))

def rout(src, capsys, **kw):
    run(src, **kw)
    return capsys.readouterr().out.strip()

# ── 1. Version ────────────────────────────────────────────────────────────────

def test_version():
    import mellowlang
    assert mellowlang.__version__ == "1.4.8"

# ── 2. Basic syntax ───────────────────────────────────────────────────────────

def test_hello(capsys):
    assert rout('show "Hello 1.4.8"', capsys) == "Hello 1.4.8"

def test_arithmetic(capsys):
    assert rout('show 2 + 3 * 4', capsys) == "14"

def test_keep(capsys):
    assert rout('keep x = 42\nshow x', capsys) == "42"

def test_let(capsys):
    assert rout('let x = 99\nshow x', capsys) == "99"

def test_if_else(capsys):
    src = 'keep x = 5\ncheck x > 3:\n    show "big"\nelse:\n    show "small"'
    assert rout(src, capsys) == "big"

def test_loop_while(capsys):
    src = 'keep i = 0\nloop i < 3:\n    keep i = i + 1\nshow i'
    assert rout(src, capsys) == "3"

def test_skill(capsys):
    src = 'skill add(a, b):\n    return a + b\nshow add(3, 4)'
    assert rout(src, capsys) == "7"

def test_fstring(capsys):
    assert rout('keep n = "World"\nshow f"Hello {n}!"', capsys) == "Hello World!"

def test_try_catch(capsys):
    src = 'try:\n    keep x = 1/0\ncatch e:\n    show "caught"'
    assert rout(src, capsys) == "caught"

def test_for_range(capsys):
    src = 'keep s = 0\nfor i = 1, 3:\n    keep s = s + i\nshow s'
    assert rout(src, capsys) == "6"

def test_for_each(capsys):
    src = 'keep xs = [10,20,30]\nkeep t = 0\nfor x in xs:\n    keep t = t + x\nshow t'
    assert rout(src, capsys) == "60"

def test_repeat_until(capsys):
    src = 'keep x = 0\nrepeat:\n    keep x = x + 1\nuntil x >= 5\nshow x'
    assert rout(src, capsys) == "5"

def test_break(capsys):
    src = 'keep i = 0\nloop i < 10:\n    keep i = i + 1\n    check i == 3:\n        break\nshow i'
    assert rout(src, capsys) == "3"

def test_boolean_ops(capsys):
    assert rout('show true and false', capsys).lower() == "false"
    assert rout('show true or false', capsys).lower() == "true"
    assert rout('show not true', capsys).lower() == "false"

def test_string_concat(capsys):
    assert rout('show "hello" + " " + "world"', capsys) == "hello world"

def test_list_literal(capsys):
    out = rout('keep xs = [1,2,3]\nshow xs', capsys)
    assert "1" in out and "3" in out

def test_map_literal(capsys):
    out = rout('keep m = {name:"mellow"}\nshow m', capsys)
    assert "mellow" in out

def test_multiprint(capsys):
    out = rout('show 1, 2, 3', capsys)
    assert "1" in out and "2" in out and "3" in out

def test_nested_skill(capsys):
    src = 'skill mul(a,b):\n    return a*b\nskill sq(n):\n    return mul(n,n)\nshow sq(5)'
    assert rout(src, capsys) == "25"

# ── 3. Stdlib (dot-call style) ────────────────────────────────────────────────

def test_math_sqrt(capsys):
    assert rout('show math.sqrt(9)', capsys).startswith("3")

def test_math_abs(capsys):
    assert rout('show math.abs(-7)', capsys) == "7"

def test_math_pi(capsys):
    assert float(rout('show math.pi', capsys)) == pytest.approx(3.14159, abs=0.001)

def test_math_clamp(capsys):
    assert rout('show math.clamp(15,0,10)', capsys) == "10"

def test_string_upper(capsys):
    assert rout('show string.upper("mellow")', capsys) == "MELLOW"

def test_string_lower(capsys):
    assert rout('show string.lower("MELLOW")', capsys) == "mellow"

def test_string_len(capsys):
    assert rout('show string.len("hello")', capsys) == "5"

def test_list_push(capsys):
    out = rout('keep xs=[1]\nlist.push(xs,2)\nshow xs', capsys)
    assert "2" in out

def test_json_encode(capsys):
    out = rout('show json.encode({x:1})', capsys)
    assert "x" in out and "1" in out

# ── 4. get/call Module System (v1.4.8) ───────────────────────────────────────

def test_get_math_sqrt(capsys):
    assert rout('keep x = get math.sqrt(25)\nshow x', capsys) == "5"

def test_call_math_sqrt(capsys):
    assert rout('keep x = call math.sqrt(36)\nshow x', capsys) == "6"

def test_get_math_abs(capsys):
    assert rout('keep x = get math.abs(-42)\nshow x', capsys) == "42"

def test_get_string_upper(capsys):
    assert rout('keep r = get string.upper("hello")\nshow r', capsys) == "HELLO"

def test_call_string_lower(capsys):
    assert rout('keep r = call string.lower("WORLD")\nshow r', capsys) == "world"

def test_get_string_len(capsys):
    assert rout('keep n = get string.len("mellowlang")\nshow n', capsys) == "10"

def test_call_string_replace(capsys):
    out = rout('keep r = call string.replace("hello world","world","mellow")\nshow r', capsys)
    assert out == "hello mellow"

def test_call_string_trim(capsys):
    assert rout('keep r = call string.trim("  hi  ")\nshow r', capsys) == "hi"

def test_get_string_contains(capsys):
    out = rout('keep r = get string.contains("mellowlang","mellow")\nshow r', capsys)
    assert out.lower() in ("true","1")

def test_get_list_len(capsys):
    assert rout('keep xs=[1,2,3,4]\nkeep n=get list.len(xs)\nshow n', capsys) == "4"

def test_get_math_clamp(capsys):
    assert rout('keep v=get math.clamp(20,0,10)\nshow v', capsys) == "10"

def test_get_math_lerp(capsys):
    out = rout('keep v=get math.lerp(0,10,0.5)\nshow v', capsys)
    assert float(out) == pytest.approx(5.0, abs=0.01)

def test_get_statement_no_assign(capsys):
    assert rout('get math.abs(-5)\nshow "ok"', capsys) == "ok"

def test_call_statement_no_assign(capsys):
    assert rout('call math.abs(-5)\nshow "ok"', capsys) == "ok"

def test_get_result_in_arithmetic(capsys):
    out = rout('keep x = get math.sqrt(16) + 1\nshow x', capsys)
    assert out == "5"

def test_get_result_in_condition(capsys):
    src = 'keep x = get math.abs(-5)\ncheck x > 3:\n    show "yes"\nelse:\n    show "no"'
    assert rout(src, capsys) == "yes"

def test_get_and_call_equivalent(capsys):
    src = 'keep a=get math.abs(-10)\nkeep b=call math.abs(-20)\nshow a\nshow b'
    lines = rout(src, capsys).split('\n')
    assert lines[0].strip() == "10"
    assert lines[1].strip() == "20"

def test_nested_get(capsys):
    out = rout('keep x=get math.sqrt(get math.abs(-9))\nshow x', capsys)
    assert out.startswith("3")

def test_get_json_encode(capsys):
    out = rout('keep j=call json.encode({key:"val"})\nshow j', capsys)
    assert "val" in out

def test_get_chain(capsys):
    src = 'keep a=get math.abs(-3)\nkeep b=get math.sqrt(a*a)\nshow b'
    out = rout(src, capsys)
    assert out.startswith("3")

def test_unknown_module_blocked(capsys):
    src = 'try:\n    keep r=get badmodule.badfunction()\ncatch e:\n    show "blocked"'
    assert rout(src, capsys) == "blocked"

def test_get_call_in_loop(capsys):
    src = '''
keep total = 0
keep xs = [1,4,9,16]
for x in xs:
    keep root = get math.sqrt(x)
    keep total = total + root
show total
'''
    out = rout(src, capsys)
    assert float(out) == pytest.approx(10.0, abs=0.01)

def test_call_ai_chat_get_keyword(capsys):
    out = rout('keep r=get ai.chat("hello")\nshow r', capsys)
    assert "response" in out

# ── 5. AI Engine (v1.4.8) ────────────────────────────────────────────────────

def test_ai_chat_basic(capsys):
    out = rout('keep r=call ai.chat("hello")\nshow r', capsys)
    assert "response" in out

def test_ai_chat_various_prompts(capsys):
    for prompt in ['"bye"', '"how are you"', '"help"', '"mellow"', '"train"']:
        out = rout(f'keep r=call ai.chat({prompt})\nshow r', capsys)
        assert "response" in out

def test_ai_model_create(capsys):
    src = 'keep m=call ai.model_create("net1",[{in:2,out:4,activation:"relu"},{in:4,out:2,activation:"softmax"}],"classify")\nshow m'
    out = rout(src, capsys)
    assert "net1" in out and "created" in out

def test_ai_train(capsys):
    src = '''
call ai.model_create("t1",[{in:2,out:3,activation:"relu"},{in:3,out:2,activation:"softmax"}],"classify")
keep r=call ai.train("t1",[[1,0],[0,1],[1,1],[0,0]],[0,1,0,1],5,0.01)
show r
'''
    out = rout(src, capsys)
    assert "trained" in out

def test_ai_predict(capsys):
    src = '''
call ai.model_create("p1",[{in:2,out:2,activation:"sigmoid"}],"classify")
call ai.train("p1",[[1,0],[0,1]],[0,1],3,0.01)
keep pred=call ai.predict("p1",[1,0])
show pred
'''
    out = rout(src, capsys)
    assert "prediction" in out

def test_ai_embed(capsys):
    out = rout('keep emb=call ai.embed("mellow")\nshow emb', capsys)
    assert "[" in out

def test_ai_model_info(capsys):
    src = 'call ai.model_create("info1",[{in:2,out:2}],"regress")\nkeep info=call ai.model_info("info1")\nshow info'
    out = rout(src, capsys)
    assert "info1" in out

def test_ai_models_list(capsys):
    src = 'call ai.model_create("listme",[{in:2,out:2}],"classify")\nkeep ns=call ai.models_list()\nshow ns'
    out = rout(src, capsys)
    assert "listme" in out

def test_ai_loss_history(capsys):
    src = '''
call ai.model_create("lh",[{in:1,out:1,activation:"linear"}],"regress")
call ai.train("lh",[[1],[2],[3]],[2.0,4.0,6.0],5,0.01)
keep hist=call ai.loss_history("lh")
show hist
'''
    out = rout(src, capsys)
    assert "[" in out

def test_ai_missing_model_error(capsys):
    out = rout('keep r=call ai.predict("none_model",[1,0])\nshow r', capsys)
    assert "error" in out.lower() or "not found" in out.lower()

def test_ai_classify_xor(capsys):
    src = '''
call ai.model_create("xor",[{in:2,out:4,activation:"relu"},{in:4,out:2,activation:"softmax"}],"classify")
keep res=call ai.train("xor",[[0,0],[0,1],[1,0],[1,1]],[0,1,1,0],50,0.05)
show res
keep pred=call ai.predict("xor",[0,1])
show pred
'''
    out = rout(src, capsys)
    assert "trained" in out and "prediction" in out

def test_ai_regress(capsys):
    src = '''
call ai.model_create("reg",[{in:1,out:1,activation:"linear"}],"regress")
call ai.train("reg",[[0],[1],[2],[3]],[0.0,1.0,2.0,3.0],20,0.01)
keep pred=call ai.predict("reg",[2])
show pred
'''
    out = rout(src, capsys)
    assert "prediction" in out

def test_ai_retrain(capsys):
    src = '''
call ai.model_create("re",[{in:2,out:2}],"classify")
call ai.train("re",[[1,0],[0,1]],[0,1],3,0.01)
keep r=call ai.train("re",[[1,0],[0,1]],[0,1],3,0.01)
show r
'''
    out = rout(src, capsys)
    assert "trained" in out

def test_ai_embed_length(capsys):
    """Embedding is always 64-dimensional."""
    src = '''
keep emb=call ai.embed("test")
keep n=get list.len(emb)
show n
'''
    out = rout(src, capsys)
    assert out.strip() == "64"

# ── 6. C VM bridge ────────────────────────────────────────────────────────────

def test_cvm_fallback():
    c = LegacyCompiler()
    bytecode = c.compile(['keep x = 2 + 3', 'show x'])
    from mellowlang.host.legacy import default_host
    run_bytecode(bytecode=bytecode, host=default_host(), config={"allow_ask": False},
                 func_table=c.functions, event_table=c.events)

def test_cvm_available_bool():
    assert isinstance(c_vm_available(), bool)

# ── 7. Full integration ───────────────────────────────────────────────────────

def test_full_workflow(capsys):
    src = '''
keep created=call ai.model_create("wf",[{in:3,out:8,activation:"relu"},{in:8,out:3,activation:"softmax"}],"classify")
show created
call ai.train("wf",[[1,0,0],[0,1,0],[0,0,1]],[0,1,2],10,0.02)
keep pred=call ai.predict("wf",[1,0,0])
show pred
keep info=call ai.model_info("wf")
show info
keep ns=call ai.models_list()
show ns
'''
    out = rout(src, capsys)
    assert "wf" in out and "prediction" in out and "layers" in out

def test_ai_with_math_modules(capsys):
    """Combine AI model and math operations."""
    src = '''
keep x = get math.sqrt(4)
keep emb = call ai.embed("test")
keep n = get list.len(emb)
show x
show n
'''
    out = rout(src, capsys)
    lines = out.strip().split('\n')
    assert lines[0].strip() == "2"
    assert lines[1].strip() == "64"
