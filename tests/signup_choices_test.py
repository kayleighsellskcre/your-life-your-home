import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
c = A.app.test_client()

t = c.get("/login").get_data(as_text=True)
ok("/signup?role=homeowner" in t and "/signup?role=agent" in t and "/signup?role=lender" in t, "the Sign In page offers a sign-up for homeowners, agents and lenders")
ok("I am a real estate agent" in t and "I am a lender" in t, "the choices say who each one is for")
for role, other in (("homeowner", ("agent", "lender")), ("agent", ("homeowner", "lender")), ("lender", ("homeowner", "agent"))):
    t = c.get(f"/signup?role={role}").get_data(as_text=True)
    ok(all(f"/signup?role={o}" in t for o in other), f"the {role} sign-up page links to the other two sign-ups")
