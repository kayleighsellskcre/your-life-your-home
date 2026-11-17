import os, sys, tempfile, io, contextlib, re
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
c = A.app.test_client()
vis = lambda t: re.sub(r"(?s)<(style|script).*?</(style|script)>", "", t)
for p, words in (("/privacy", "never sell"), ("/terms", "not an appraisal"), ("/pricing", "$29/mo")):
    r = c.get(p); t = r.get_data(as_text=True)
    ok(r.status_code == 200 and words in t, f"{p} opens and says what it should")
    ok(chr(8212) not in vis(t), f"no em dashes on {p}")
t = c.get("/pricing").get_data(as_text=True)
ok("Free" in t and "$29/mo" in t and "Homeowners" in t, "pricing shows homeowners free plus the paid plan")
h = c.get("/").get_data(as_text=True)
ok("/pricing" in h and "/privacy" in h and "/terms" in h, "the footer links Pricing, Privacy and Terms")
ok("lending professionals" not in h and "and lenders" in h, "the Journey line says lenders")
for p in ("/agents", "/lenders"):
    ok("/pricing" in c.get(p).get_data(as_text=True), f"{p} links to pricing")
ok("/pricing" not in c.get("/homeowners").get_data(as_text=True).split("<footer")[0], "the homeowner page does not push pricing")
ok("@media (max-width: 480px)" in h and "clamp(.95rem,4.9vw" in h, "the phone header rules are in place")
