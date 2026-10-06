# package-registry MCP server (stand-in for DevRel's server)

DevRel's real package-registry MCP server is not in this repo and was not
supplied with the Week 9 brief. `server.py` is a **local stand-in** with the
same job (version metadata, release dates, deprecation notices) over an
offline fixture (`packages.json`). It is treated as THIRD-PARTY code: the
agent (`src/mcp_agent.py`) never imports it, only launches it from
`mcp_config.json`. It deliberately behaves like a typical third-party
server (logs full arguments, wants a token in env) so the supply-chain audit
in `risk_note.md` has real behavior to look at.
