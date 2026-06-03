# Added AI runtime tests
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mellowlang.compiler import Compiler
from mellowlang.vm.vm import MellowVM, RunConfig


def run(src, **kw):
    c = Compiler(); vm = MellowVM()
    prog = c.compile(src)
    vm.run(prog, config=RunConfig(**kw))


def rout(src, capsys, **kw):
    run(src, **kw)
    return capsys.readouterr().out.strip()


def test_ai_runtime_boot_and_info(capsys):
    out = rout('keep a=call ai.runtime_boot({"mode":"offline"})\nkeep b=call ai.runtime_info()\nshow a\nshow b', capsys)
    assert "ready" in out
    assert "booted" in out


def test_ai_session_roundtrip(capsys):
    out = rout('keep s=call ai.session_open("test")\nkeep sid=s["session"]\nkeep r=call ai.session_message(sid,"hello")\nkeep h=call ai.session_history(sid)\nshow r\nshow h', capsys)
    assert "response" in out
    assert "messages" in out


def test_ai_prompt_template_and_vector_search(capsys):
    out = rout('keep p=call ai.prompt_template("Hi {{name}}",{"name":"Mellow"})\nkeep v=call ai.vector_search("offline",["offline ai runtime","math helpers"],1)\nshow p\nshow v', capsys)
    assert "Hi Mellow" in out
    assert "offline ai runtime" in out


def test_ai_rag_answer(capsys):
    out = rout('keep r=call ai.rag_answer("runtime",["offline ai runtime","game helpers"],1)\nshow r', capsys)
    assert "Offline RAG summary" in out
