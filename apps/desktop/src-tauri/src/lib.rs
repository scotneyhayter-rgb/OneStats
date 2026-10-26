// OneStats desktop shell.
//
// In the standalone Windows build, the app launches the packaged backend as a *sidecar*
// (onestats-server.exe) on startup and terminates it on exit, so the user never starts Python,
// FastAPI or a terminal. The backend binds to loopback only and brings up the local database and
// migrations itself (see services/api/onestats/standalone/launcher.py).
//
// In development the sidecar binary is not bundled; spawning is skipped and the app talks to the
// separately-running dev backend, so `npm run tauri dev` keeps working unchanged.

use std::sync::Mutex;

use tauri::{Manager, RunEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// Holds the backend sidecar child so it can be shut down cleanly when the app exits.
struct BackendProcess(Mutex<Option<CommandChild>>);

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

fn spawn_backend(app: &tauri::AppHandle) {
    match app.shell().sidecar("onestats-server") {
        Ok(cmd) => match cmd.spawn() {
            Ok((mut rx, child)) => {
                if let Some(state) = app.try_state::<BackendProcess>() {
                    *state.0.lock().unwrap() = Some(child);
                }
                // Drain the backend's output so the pipe never blocks; useful for diagnostics.
                tauri::async_runtime::spawn(async move {
                    while let Some(event) = rx.recv().await {
                        match event {
                            CommandEvent::Stdout(bytes) | CommandEvent::Stderr(bytes) => {
                                eprint!("[onestats-server] {}", String::from_utf8_lossy(&bytes));
                            }
                            _ => {}
                        }
                    }
                });
            }
            Err(e) => eprintln!("OneStats: failed to start backend sidecar: {e}"),
        },
        // No bundled sidecar (development) — the app uses the separately-running dev backend.
        Err(e) => eprintln!("OneStats: backend sidecar not bundled (dev mode): {e}"),
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            spawn_backend(app.handle());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![greet])
        .build(tauri::generate_context!())
        .expect("error while running tauri application");

    app.run(|app_handle, event| {
        // On exit, stop the backend sidecar so no orphaned process is left running.
        if let RunEvent::ExitRequested { .. } = event {
            if let Some(state) = app_handle.try_state::<BackendProcess>() {
                if let Some(child) = state.0.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        }
    });
}
