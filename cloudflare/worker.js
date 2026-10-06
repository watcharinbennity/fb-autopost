// ตัวปลุกบอท fb-autopost ทุก 15 นาที (Cloudflare Workers Cron Trigger)
// GitHub cron มักช้าหลายชั่วโมง/หายไป จึงให้ Cloudflare สั่งรัน workflow แทน
// ตัว workflow + scheduler.py จะตัดสินเองว่าถึงรอบโพสต์หรือยัง (ไม่ถึงรอบ = จบใน ~15 วินาที)
//
// ตั้งค่าใน Cloudflare:
//   Settings → Variables and Secrets → เพิ่ม Secret ชื่อ GH_TOKEN (GitHub fine-grained token)
//   Settings → Triggers → Cron Triggers → เพิ่ม  */15 * * * *

const REPO = "watcharinbennity/fb-autopost";

const JOBS = [
  { workflow: "main.yml", inputs: { dry_run: "false", via_cron: "true" } },
  { workflow: "reels.yml", inputs: { action: "post", page: "all", via_cron: "true" } },
];

async function dispatch(env, job) {
  const res = await fetch(
    `https://api.github.com/repos/${REPO}/actions/workflows/${job.workflow}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GH_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "fb-autopost-cron",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref: "main", inputs: job.inputs }),
    }
  );
  const text = res.status === 204 ? "" : await res.text();
  return `${job.workflow}: ${res.status} ${text.slice(0, 200)}`;
}

async function runAll(env) {
  const out = [];
  for (const job of JOBS) {
    out.push(await dispatch(env, job));
  }
  return out.join("\n");
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(runAll(env).then((r) => console.log(r)));
  },
  // เปิด URL ของ worker เพื่อทดสอบด้วยมือ (ไม่โพสต์ถ้ายังไม่ถึงรอบ)
  async fetch(request, env) {
    if (!env.GH_TOKEN) return new Response("missing GH_TOKEN secret", { status: 500 });
    return new Response(await runAll(env), { headers: { "content-type": "text/plain; charset=utf-8" } });
  },
};
