from mellowlang.playground.server import start_debug_session, debugger_command


def test_full_debugger_session_steps():
    source = 'print("hello")\nkeep score = 0\nscore = score + 1\nprint(score)\n'
    started = start_debug_session(source, watch='score')
    assert started['paused'] is True
    assert started['stop']['pc'] == 0
    assert started['stop']['opcode']

    step1 = debugger_command(started['session_id'], 'step_into')
    assert step1['paused'] is True
    assert step1['stop']['pc'] >= 1
    assert 'stack' in step1['stop']
    assert 'locals' in step1['stop']
    assert 'frames' in step1['stop']

    step2 = debugger_command(started['session_id'], 'step_over')
    assert step2['paused'] is True
    assert step2['stop']['pc'] >= step1['stop']['pc']

    done = debugger_command(started['session_id'], 'continue')
    assert done['finished'] is True
