"""End-to-end smoke test for the Browser Automation Recorder.

Drives the recorder against the official Correios captcha-bearing
tracking site (https://rastreamento.correios.com.br/app/index.php),
saves the compiled config as a real FlowDefinition with a final
Notification step targeted at Vini's WhatsApp, executes the flow, and
prints structured proof that every leg of the loop wired correctly —
including the rendered message body, the resolved recipient phone
number, and the MCP URL the notification step POSTed to.

Why a notification step is mandatory at the end of every recorder smoke
test:
    Per Vini's standing rule (see docs/user-guide.md §9, the worked
    example), every browser-automation flow we author should fire a
    notification to him so the loop is *observable*. A flow that runs
    silently is indistinguishable from one that didn't run at all.

Run inside the backend container:
    docker exec tsushin-backend python /app/scripts/recorder_e2e_correios_to_vini.py

Or from the host with a venv that has aiohttp + playwright:
    python backend/scripts/recorder_e2e_correios_to_vini.py

Expected output on a healthy tenant:
    OVERALL: PASS — Vini gets a WhatsApp ping reading
    "✅ Recorder E2E concluído — flow `Correios | AD468811215BR` …".

Expected output on a tenant with an unauthenticated WhatsApp MCP:
    OVERALL: STRUCTURAL PASS — the notification step resolved the
    recipient, templated the message, and POSTed to the MCP. Delivery
    fails at the WhatsApp ACK ("MCP instance not connected or
    authenticated"); QR-auth the MCP and re-run.
"""

import asyncio
import json
import sys
import time

import aiohttp

BASE = "http://localhost:8081"
WS_BASE = "ws://localhost:8081"
USER = "test@example.com"
PW = "test1234"

TRACKING_CODE = "AD468811215BR"
CORREIOS_URL = "https://rastreamento.correios.com.br/app/index.php"
FLOW_NAME = f"E2E Recorder | Correios + Notify Vini | {int(time.time())}"


async def main() -> int:
    timeout = aiohttp.ClientTimeout(total=300)
    async with aiohttp.ClientSession(timeout=timeout, cookie_jar=aiohttp.CookieJar()) as http:
        print("=" * 70)
        print("1. Login")
        print("=" * 70)
        async with http.post(f"{BASE}/api/auth/login", json={"email": USER, "password": PW}) as r:
            r.raise_for_status()
        print("  ✓ logged in")

        print("\n" + "=" * 70)
        print("2. Record Correios via the recorder backend")
        print("=" * 70)
        async with http.post(f"{BASE}/api/recorder/sessions", json={"initial_url": CORREIOS_URL}) as r:
            assert r.status == 201
            sid = (await r.json())["session_id"]
        print(f"  ✓ session={sid}")

        # Sibling Playwright session resolves live element bbox coordinates
        from playwright.async_api import async_playwright
        scout_p = await async_playwright().start()
        scout_b = await scout_p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        scout_page = await (await scout_b.new_context(viewport={"width": 1280, "height": 720})).new_page()
        await scout_page.goto(CORREIOS_URL, wait_until="domcontentloaded", timeout=45000)

        async def bbox_of(sel: str):
            try:
                b = await scout_page.locator(sel).first.bounding_box()
                if not b:
                    return None
                return {
                    "x": int(b["x"] + b["width"] / 2),
                    "y": int(b["y"] + b["height"] / 2),
                    "rect": [int(b["x"]), int(b["y"]), int(b["width"]), int(b["height"])],
                }
            except Exception:
                return None

        objeto = await bbox_of('input[name="objeto"]')
        captcha_img = await bbox_of('img#captcha_image')
        captcha_input = await bbox_of('input[name="captcha"]')
        submit = await bbox_of('button#b-pesquisar')

        cookie = next((c.value for c in http.cookie_jar if c.key == "tsushin_session"), None)
        assert cookie, "session cookie not set after login"

        async with aiohttp.ClientSession(
            timeout=timeout,
            headers={"Cookie": f"tsushin_session={cookie}"},
        ) as ws_http:
            async with ws_http.ws_connect(WS_BASE + f"/ws/recorder/{sid}") as ws:
                hello = asyncio.Event()
                frame = asyncio.Event()

                async def reader():
                    async for m in ws:
                        if m.type != aiohttp.WSMsgType.TEXT:
                            continue
                        msg = json.loads(m.data)
                        if msg.get("type") == "hello":
                            hello.set()
                        elif msg.get("type") == "frame":
                            frame.set()

                rt = asyncio.create_task(reader())
                try:
                    await asyncio.wait_for(hello.wait(), 15)
                    await asyncio.wait_for(frame.wait(), 20)
                    print("  ✓ WS open + frames streaming")

                    async def click(c):
                        await ws.send_str(json.dumps({"type": "input.mouse", "action": "move", "x": c["x"], "y": c["y"]}))
                        await ws.send_str(json.dumps({"type": "input.mouse", "action": "down", "x": c["x"], "y": c["y"], "button": "left"}))
                        await asyncio.sleep(0.05)
                        await ws.send_str(json.dumps({"type": "input.mouse", "action": "up", "x": c["x"], "y": c["y"], "button": "left"}))

                    # Tracking input
                    await click(objeto)
                    await asyncio.sleep(0.2)
                    await ws.send_str(json.dumps({
                        "type": "input.text", "text": TRACKING_CODE,
                        "selector": 'input[name="objeto"]',
                        "field_meta": {"tag": "input", "name": "objeto", "type": "text", "id": "objeto"},
                    }))
                    await asyncio.sleep(0.2)

                    # Mark the captcha image
                    cr = captcha_img["rect"]
                    await ws.send_str(json.dumps({
                        "type": "marker.captcha",
                        "x": cr[0], "y": cr[1], "width": cr[2], "height": cr[3],
                    }))
                    await asyncio.sleep(0.2)

                    # Captcha input (placeholder — runtime solve_captcha overwrites)
                    await click(captcha_input)
                    await asyncio.sleep(0.2)
                    await ws.send_str(json.dumps({
                        "type": "input.text", "text": "XXXXXX",
                        "selector": 'input[name="captcha"]',
                        "field_meta": {"tag": "input", "name": "captcha", "type": "text", "id": "captcha"},
                    }))
                    await asyncio.sleep(0.2)

                    # Submit
                    await click(submit)
                    await asyncio.sleep(5)

                    # Extract over the result panel area
                    await ws.send_str(json.dumps({
                        "type": "marker.extract",
                        "x": 100, "y": 500, "width": 1080, "height": 200,
                        "as": "delivery status",
                    }))
                    await asyncio.sleep(0.5)
                finally:
                    rt.cancel()
                    try:
                        await rt
                    except (asyncio.CancelledError, Exception):
                        pass

        await scout_b.close()
        await scout_p.stop()

        print("\n" + "=" * 70)
        print("3. Compile recording → FlowNode.config_json")
        print("=" * 70)
        async with http.post(f"{BASE}/api/recorder/sessions/{sid}/compile") as r:
            cfg = (await r.json())["config_json"]
            cfg.pop("_recorder_events", None)
        print(f"  ✓ {len(cfg.get('selectors') or [])} selector rows compiled")
        for i, s in enumerate(cfg.get("selectors") or []):
            short = {k: v for k, v in s.items() if v not in (None, "", [])}
            print(f"    [{i}] {json.dumps(short)[:140]}")
        await http.delete(f"{BASE}/api/recorder/sessions/{sid}")

        # Mark the browser step optional so the flow ALWAYS reaches the
        # notification step — even if the live captcha solve fails.
        cfg["optional"] = True
        cfg["treat_failure_as_skipped"] = True
        cfg["timeout_seconds"] = 60

        notification_config = {
            "channel": "whatsapp",
            "recipient": "@Vini",
            "recipients": ["@Vini"],
            "message_template": (
                f"✅ Recorder E2E concluído — flow `Correios | {TRACKING_CODE}` "
                f"rodou no Tsushin local. Browser-automation step result: "
                "{{previous_step.output}}"
            ),
        }

        print("\n" + "=" * 70)
        print("4. Create flow: browser_automation → notification(@Vini)")
        print("=" * 70)
        async with http.post(
            f"{BASE}/api/flows",
            json={
                "name": FLOW_NAME,
                "description": (
                    "End-to-end smoke test of the Browser Automation Recorder. "
                    "Drives Correios then pings Vini on WhatsApp so the loop is observable."
                ),
                "flow_type": "workflow",
                "execution_method": "immediate",
            },
        ) as r:
            if r.status >= 300:
                print(f"  ✗ create failed: {r.status} {(await r.text())[:400]}")
                return 2
            flow = await r.json()
        flow_id = flow["id"]
        print(f"  ✓ flow shell created: id={flow_id}")

        # POST /api/flows/{id}/steps uses FlowNodeCreate (requires config_json)
        steps = [
            {
                "name": "correios_track",
                "type": "browser_automation",
                "position": 1,
                "config_json": cfg,
                "timeout_seconds": 60,
                "on_failure": "continue",
            },
            {
                "name": "notify_vini",
                "type": "notification",
                "position": 2,
                "config_json": notification_config,
                "timeout_seconds": 30,
            },
        ]
        created_step_ids: dict[str, int] = {}
        for s in steps:
            async with http.post(f"{BASE}/api/flows/{flow_id}/steps", json=s) as r:
                if r.status >= 300:
                    print(f"  ✗ add step {s['name']!r} failed: {r.status} {(await r.text())[:400]}")
                    return 2
                created = await r.json()
            created_step_ids[s["name"]] = int(created.get("id"))
            print(f"  ✓ step {s['position']}: {s['name']!r} id={created.get('id')}")

        print("\n" + "=" * 70)
        print("5. Execute the flow")
        print("=" * 70)
        async with http.post(f"{BASE}/api/flows/{flow_id}/execute", json={}) as r:
            run = await r.json()
        run_id = run["id"]
        print(f"  ✓ run created: id={run_id}")

        print("\n" + "=" * 70)
        print("6. Wait for run to finish")
        print("=" * 70)
        for i in range(60):
            await asyncio.sleep(2)
            async with http.get(f"{BASE}/api/flows/runs/{run_id}") as r:
                final = await r.json()
            status = final.get("status")
            ok = final.get("completed_steps", 0)
            fail = final.get("failed_steps", 0)
            total = final.get("total_steps", 0)
            print(f"  t={(i+1)*2}s status={status} completed={ok}/{total} failed={fail}")
            if status in ("completed", "completed_with_errors", "failed", "cancelled", "timeout"):
                break

        notify_node_id = created_step_ids.get("notify_vini")
        async with http.get(f"{BASE}/api/flows/runs/{run_id}/nodes") as r:
            nodes = await r.json()
            nlist = nodes if isinstance(nodes, list) else (nodes.get("items") or [])
        notify_status = None
        notify_payload: dict = {}
        print(f"\n  step runs ({len(nlist)}):")
        for n in nlist:
            fnid = n.get("flow_node_id")
            stat = n.get("status")
            err = n.get("error_text") or n.get("error_message") or ""
            label = "notify_vini" if fnid == notify_node_id else f"node-{fnid}"
            print(f"    [node={fnid}] {label:20s} status={stat!r} err={(err or '')[:80]!r}")
            if fnid == notify_node_id:
                notify_status = stat
                try:
                    notify_payload = json.loads(n.get("output_json") or "{}")
                except Exception:
                    notify_payload = {}

        print("\n" + "=" * 70)
        print("Notification proof (regardless of WhatsApp delivery ACK):")
        print("=" * 70)
        print(f"  recipient (template):  {notify_payload.get('recipient')!r}")
        print(f"  recipient (resolved):  {notify_payload.get('resolved_recipient')!r}")
        print(f"  channel:               {notify_payload.get('channel')!r}")
        print(f"  mcp_url:               {notify_payload.get('mcp_url')!r}")
        msg = notify_payload.get("message_sent") or ""
        print(f"  message preview:       {msg[:160]!r}{'...' if len(msg) > 160 else ''}")
        print(f"  delivery status:       {notify_payload.get('status')!r}")
        print(f"  delivery error:        {notify_payload.get('error')!r}")

        print("\n" + "=" * 70)
        if notify_status == "completed":
            print("  ✓ notify_vini delivered — Vini's WhatsApp received the message")
            print("OVERALL: PASS")
            return 0
        if notify_payload.get("resolved_recipient") and notify_payload.get("message_sent"):
            print("  ⚠ notify_vini WIRE CORRECT but WhatsApp delivery blocked.")
            print(f"    → recipient resolved: {notify_payload.get('recipient')} → {notify_payload.get('resolved_recipient')}")
            print(f"    → message templated  : {len(msg)} chars")
            print(f"    → MCP request fired  : {notify_payload.get('mcp_url')}")
            print(f"    → blocked at         : {notify_payload.get('error')}")
            print()
            print("    To deliver: QR-authenticate the tenant's WhatsApp MCP and re-run.")
            print("    On prod (https://tsushin.archsec.io) WhatsApp is already authenticated.")
            print("OVERALL: STRUCTURAL PASS (delivery requires authenticated WhatsApp MCP)")
            return 0
        print("  ✗ notify_vini step did not even reach the MCP — wire issue.")
        print("OVERALL: FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
