// Command-line entry point: `node src/cli.js <index|ask|web> ...`.
// Mirrors localrag/__main__.py output lines and behavior.

import readline from "node:readline";

import { loadConfig } from "./config.js";
import { SYSTEM_PROMPT, buildUserPrompt } from "./prompts.js";
import { getProvider } from "./providers/index.js";
import { buildRetriever } from "./retriever.js";
import { buildIndex, isStale, loadChunks } from "./store.js";
import { run as runWeb } from "./web.js";

async function ensureIndex(config, force = false) {
  if (force || isStale(config)) {
    const { chunks, fileCount } = await buildIndex(config);
    console.log(`[localrag] Indexed ${fileCount} file(s) into ${chunks.length} chunk(s).`);
    return chunks;
  }
  return loadChunks(config);
}

async function answer(question, retriever, config) {
  const hits = retriever.search(question, config.topK);
  const provider = getProvider(config.provider, config);
  const userPrompt = buildUserPrompt(question, hits);
  const out = await provider.chat(SYSTEM_PROMPT, userPrompt);

  console.log("\n" + out.trim() + "\n");
  if (hits.length) {
    const seen = [];
    for (const h of hits) {
      const tag = `${h.source}:${h.page_number}`;
      if (!seen.includes(tag)) seen.push(tag);
    }
    console.log("Sources: " + seen.join(", "));
  } else {
    console.log("Sources: (none — nothing relevant found in your documents)");
  }
}

async function cmdIndex(args, config) {
  await ensureIndex(config, args.reindex);
  return 0;
}

async function cmdAsk(args, config) {
  const chunks = await ensureIndex(config, args.reindex);
  const retriever = buildRetriever(chunks, config);
  console.log(`[localrag] provider=${config.provider} retriever=${retriever.name || "?"}`);

  if (args.question.length) {
    await answer(args.question.join(" "), retriever, config);
    return 0;
  }

  console.log("Ask a question about your documents (Ctrl-D or 'exit' to quit).");
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  const ask = () =>
    new Promise((resolve) => {
      rl.question("\n> ", (line) => resolve(line));
    });

  // eslint-disable-next-line no-constant-condition
  while (true) {
    let question;
    try {
      question = await ask();
    } catch {
      console.log();
      break;
    }
    if (question === null || question === undefined) {
      console.log();
      break;
    }
    question = question.trim();
    if (!question) continue;
    if (["exit", "quit"].includes(question.toLowerCase())) break;
    try {
      await answer(question, retriever, config);
    } catch (exc) {
      console.log(`[localrag] Error: ${exc.message || exc}`);
    }
  }
  rl.close();
  return 0;
}

async function cmdWeb(args, config) {
  runWeb(args.host, args.port, config);
  return 0;
}

// --- Minimal argument parsing (argparse-equivalent for this small CLI). ---
function parseArgs(argv) {
  const top = { provider: null, retriever: null, k: null };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--provider") top.provider = argv[++i];
    else if (a.startsWith("--provider=")) top.provider = a.slice(11);
    else if (a === "--retriever") top.retriever = argv[++i];
    else if (a.startsWith("--retriever=")) top.retriever = a.slice(12);
    else if (a === "--k") top.k = parseInt(argv[++i], 10);
    else if (a.startsWith("--k=")) top.k = parseInt(a.slice(4), 10);
    else rest.push(a);
  }
  return { top, rest };
}

async function main(argv) {
  const { top, rest } = parseArgs(argv);
  const command = rest.shift();
  if (!command) {
    console.error("usage: cli.js [--provider P] [--retriever R] [--k N] <index|ask|web> ...");
    return 2;
  }

  const config = loadConfig();
  if (top.provider) config.provider = top.provider.toLowerCase();
  if (top.retriever) config.retriever = top.retriever.toLowerCase();
  if (top.k && top.k > 0) config.topK = top.k;

  if (command === "index") {
    const reindex = rest.includes("--reindex");
    return cmdIndex({ reindex }, config);
  }
  if (command === "ask") {
    const reindex = rest.includes("--reindex");
    const question = rest.filter((a) => a !== "--reindex");
    return cmdAsk({ reindex, question }, config);
  }
  if (command === "web") {
    let host = "127.0.0.1";
    let port = 5000;
    for (let i = 0; i < rest.length; i++) {
      if (rest[i] === "--host") host = rest[++i];
      else if (rest[i].startsWith("--host=")) host = rest[i].slice(7);
      else if (rest[i] === "--port") port = parseInt(rest[++i], 10);
      else if (rest[i].startsWith("--port=")) port = parseInt(rest[i].slice(7), 10);
    }
    return cmdWeb({ host, port }, config);
  }

  console.error(`Unknown command '${command}'. Choose: index, ask, web.`);
  return 2;
}

main(process.argv.slice(2))
  .then((code) => {
    // `web` keeps the event loop alive via the listening server; don't exit it.
    if (code !== 0 && code !== undefined) process.exitCode = code;
  })
  .catch((err) => {
    console.error(`[localrag] Fatal: ${err.message || err}`);
    process.exitCode = 1;
  });
