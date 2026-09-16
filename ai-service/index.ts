// AI Assistant mini-service — runs on port 3001
// Provides /api/ai endpoint that proxies to z-ai-web-dev-sdk (free LLM)
// The Python IPTV app's frontend calls this via: /api/ai?XTransformPort=3001

import { createServer } from "http";
import { URL } from "url";

const PORT = 3001;

const server = createServer(async (req, res) => {
  // CORS headers
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  if (req.method === "OPTIONS") {
    res.writeHead(204);
    res.end();
    return;
  }

  const url = new URL(req.url!, `http://localhost:${PORT}`);

  if (url.pathname === "/api/ai" && req.method === "GET") {
    const prompt = url.searchParams.get("p") || "";
    if (!prompt || prompt.length < 2) {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "No prompt provided" }));
      return;
    }
    try {
      const ZAI = (await import("z-ai-web-dev-sdk")).default;
      const zai = await ZAI.create();
      const response = await zai.chat.completions.create({
        messages: [
          {
            role: "system",
            content:
              "You are a helpful AI assistant integrated into Sg_ent_media_radio, an IPTV/media dashboard. " +
              "Keep answers concise (under 200 words). Be friendly and helpful for users aged 35-65. " +
              "You can help with: general questions, word definitions, trivia, recipe suggestions, " +
              "movie recommendations, tech help, and casual conversation.",
          },
          { role: "user", content: prompt },
        ],
        thinking: { type: "disabled" },
      });
      const content = response.choices[0]?.message?.content || "No response";
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ response: content }));
    } catch (e: any) {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: e.message || "AI error" }));
    }
    return;
  }

  // Health check
  if (url.pathname === "/healthz") {
    res.writeHead(200, { "Content-Type": "text/plain" });
    res.end("ok");
    return;
  }

  res.writeHead(404, { "Content-Type": "text/plain" });
  res.end("404");
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`[AI Service] running on port ${PORT}`);
});
