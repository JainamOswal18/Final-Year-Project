"""Headless UI smoke test with Streamlit's AppTest."""
from streamlit.testing.v1 import AppTest

at = AppTest.from_file("../app.py", default_timeout=120).run()
at.sidebar.radio[0].set_value("Data").run()
[b for b in at.button if "synthetic" in b.label][0].click().run()
print("data page exceptions:", [e.value for e in at.exception], "| success:", [s.value for s in at.success])

at.sidebar.radio[0].set_value("Chat").run()
print("chat exceptions:", [e.value for e in at.exception])
at.chat_input[0].set_value("Compare profit across categories").run()
print("exceptions:", [e.value for e in at.exception])
print("messages:", len(at.session_state.messages))
q, res = at.session_state.messages[-1]
print(q, "->", res.chart.type, f"{res.timings_ms['total']:.0f} ms")
at.chat_input[0].set_value("now only for 2025").run()
q, res = at.session_state.messages[-1]
print(q, "->", res.error or (res.chart.type, res.frame.time.start if res.frame.time else None, res.frame.intent))
