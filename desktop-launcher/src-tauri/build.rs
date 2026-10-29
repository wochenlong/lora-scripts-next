fn main() {
    println!("cargo:rerun-if-env-changed=NEXT_TRAINER_BUNDLED_FRONTEND");
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
    tauri_build::build()
}
