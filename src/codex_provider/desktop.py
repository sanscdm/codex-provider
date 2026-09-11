from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .core import ProviderError


def jxa_source(executable: Path) -> str:
    executable_literal = json.dumps(str(executable))
    return f'''ObjC.import("stdlib");

function shellQuote(value) {{
  return "'" + String(value).replace(/'/g, "'\\\"'\\\"'") + "'";
}}

function run() {{
  const app = Application.currentApplication();
  app.includeStandardAdditions = true;
  const executable = {executable_literal};

  try {{
    const rawNames = app.doShellScript(shellQuote(executable) + " names");
    const profiles = rawNames ? rawNames.split("\\n").filter(Boolean) : [];
    const actions = ["Restore original", "Use Codex defaults", "Rollback previous switch"];
    const choices = actions.concat(profiles.map(name => "Use profile: " + name));
    const picked = app.chooseFromList(choices, {{
      withTitle: "Codex Provider Switcher",
      withPrompt: "Choose the provider selection for new desktop tasks:",
      okButtonName: "Apply",
      cancelButtonName: "Cancel"
    }});
    if (!picked) return;

    const choice = picked[0];
    let command;
    if (choice === actions[0]) command = "restore";
    else if (choice === actions[1]) command = "default";
    else if (choice === actions[2]) command = "rollback";
    else command = "use " + shellQuote(choice.slice("Use profile: ".length));

    const result = app.doShellScript(shellQuote(executable) + " " + command);
    app.displayDialog(result + "\\n\\nFully quit and reopen Codex, then start a new task.", {{
      withTitle: "Codex Provider Switcher",
      buttons: ["OK"],
      defaultButton: "OK"
    }});
  }} catch (error) {{
    app.displayDialog(String(error), {{
      withTitle: "Codex Provider Switcher",
      buttons: ["OK"],
      defaultButton: "OK",
      withIcon: "stop"
    }});
  }}
}}
'''


def install_desktop_app(executable: Path, destination: Path, force: bool = False) -> Path:
    compiler = shutil.which("osacompile")
    if compiler is None:
        raise ProviderError("osacompile is required; desktop installation supports macOS only")
    if destination.exists() and not force:
        raise ProviderError(f"Desktop app already exists: {destination}. Use --force to replace it.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="codex-provider-app-") as temporary_directory:
        temporary_root = Path(temporary_directory)
        source = temporary_root / "main.js"
        built_app = temporary_root / destination.name
        source.write_text(jxa_source(executable), encoding="utf-8")
        subprocess.run(
            [compiler, "-l", "JavaScript", "-o", str(built_app), str(source)],
            check=True,
            capture_output=True,
            text=True,
        )
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(built_app, destination)
    return destination


def default_app_path() -> Path:
    return Path.home() / "Applications" / "Codex Provider Switcher.app"


def current_executable() -> Path:
    executable = shutil.which("codex-provider")
    if executable:
        return Path(executable).resolve()
    return Path(os.path.abspath(os.sys.argv[0]))
