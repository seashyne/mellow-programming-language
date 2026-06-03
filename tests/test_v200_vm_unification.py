from mellowlang.playground.server import start_debug_session, debugger_command


def test_conditional_break_and_watch_expressions():
    source = """keep score = 0
score = score + 1
score = score + 1
print(score)
"""
    started = start_debug_session(
        source,
        watch='score',
        break_when='score == 2',
        watch_exprs='score * 10; stack_depth',
    )
    assert started['paused'] is True
    assert started['stop']['typed_stack'] == []
    step1 = debugger_command(started['session_id'], 'continue')
    assert step1['paused'] is True
    assert step1['stop']['reason'] == 'conditional_breakpoint'
    assert step1['stop']['watch_expressions']['score * 10'] == 20
    assert 'typed_locals' in step1['stop']
    assert 'typed_globals' in step1['stop']
    assert 'source_span' in step1['stop']
    assert step1['debug_capabilities']['conditional_breakpoints'] is True
