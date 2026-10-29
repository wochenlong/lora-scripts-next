fn main() {
    println!("cargo:rerun-if-env-changed=NEXT_TRAINER_UPDATER_SHA256");
    println!("cargo:rerun-if-env-changed=NEXT_TRAINER_UPDATER_BYTES");
    println!("cargo:rerun-if-env-changed=NEXT_TRAINER_BUNDLED_FRONTEND");
    match (
        std::env::var("NEXT_TRAINER_UPDATER_SHA256").ok(),
        std::env::var("NEXT_TRAINER_UPDATER_BYTES").ok(),
    ) {
        (None, None) => {}
        (Some(sha), Some(bytes)) => {
            assert!(
                sha.len() == 64
                    && sha
                        .bytes()
                        .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
                "updater SHA256 must be 64 lowercase hexadecimal characters"
            );
            assert!(
                bytes.parse::<u64>().is_ok_and(|n| n > 0),
                "updater byte length must be positive"
            );
        }
        _ => panic!("updater SHA256 and byte length must be provided together"),
    }
    let output = std::path::PathBuf::from(std::env::var_os("OUT_DIR").expect("OUT_DIR"));
    let generated = if let Some(input) = std::env::var_os("NEXT_TRAINER_BUNDLED_FRONTEND") {
        let input = std::path::PathBuf::from(input);
        assert!(
            input.is_absolute() && input.is_file(),
            "bundled frontend must be an existing absolute file"
        );
        println!("cargo:rerun-if-changed={}", input.display());
        let target = output.join("frontend.zip");
        std::fs::copy(&input, &target).expect("copy bundled frontend");
        format!("pub const FRONTEND: &[u8] = include_bytes!({:?});", target)
    } else {
        "pub const FRONTEND: &[u8] = &[];".into()
    };
    std::fs::write(output.join("bundled_assets.rs"), generated).expect("write bundled identity");
    let mut engine_assets = String::new();
    for (directory, constant, suffix) in [
        ("../catalog/engines", "ENGINE_LOCKS", "json"),
        ("../catalog/engine-wheels", "ENGINE_WHEELS", "whl"),
    ] {
        println!("cargo:rerun-if-changed={directory}");
        engine_assets.push_str(&format!("const {constant}: &[(&str, &[u8])] = &[\n"));
        let mut paths: Vec<_> = std::fs::read_dir(directory)
            .into_iter()
            .flatten()
            .map(|entry| entry.expect("catalog entry").path())
            .filter(|path| path.extension().is_some_and(|ext| ext == suffix))
            .collect();
        paths.sort();
        for path in paths {
            let key = if suffix == "json" {
                path.file_stem()
            } else {
                path.file_name()
            }
            .expect("catalog filename")
            .to_str()
            .expect("UTF8 filename");
            let absolute = path.canonicalize().expect("catalog asset");
            engine_assets.push_str(&format!("({key:?}, include_bytes!({absolute:?})),\n"));
        }
        engine_assets.push_str("];\n");
    }
    std::fs::write(output.join("engine_assets.rs"), engine_assets).expect("write engine identity");
    tauri_build::build()
}
