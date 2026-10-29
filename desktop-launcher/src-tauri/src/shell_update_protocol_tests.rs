use super::*;
struct Fixture {
    root: PathBuf,
    tx: PathBuf,
    asset: Identity,
    proof: Value,
}
impl Fixture {
    fn new() -> Self {
        let root = std::env::temp_dir().join(format!(
            "launcher-m5-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        let tx = root.join("updates/shell/shell-update-fixture");
        fs::create_dir_all(root.join("state")).unwrap();
        fs::create_dir_all(root.join("profiles/default/user_data")).unwrap();
        fs::write(root.join(".launcher-workspace"), b"next-trainer-desktop-v1").unwrap();
        fs::write(root.join(".launcher-lock"), b"").unwrap();
        fs::write(
            root.join("state/registry.json"),
            b"{\"schema_version\":1, \"sentinel\":\"original bytes\"}\r\n",
        )
        .unwrap();
        fs::write(
            root.join("profiles/default/profile.json"),
            b"{\"schema_version\":1,\"id\":\"default\"}",
        )
        .unwrap();
        let asset = Identity {
            bytes: 7,
            sha256: hash(b"fixture"),
        };
        let fixtures: Value =
            serde_json::from_str(include_str!("../../catalog/signed-fixtures-v1.json")).unwrap();
        let session = json!({"schema_version":1,"root_absolute":root,"fixture_id":"signed-catalog-v1","shell_sha256":asset.sha256,"opened_at":now(),"endpoint":"embedded://signed-catalog-v1","root_key_id":ROOT_KEY_ID,"root_public_key_hex":ROOT_KEY});
        write_json(
            &root,
            &root.join("state/signed-catalog-session.json"),
            &session,
        )
        .unwrap();
        let session_bytes =
            read(&root.join("state/signed-catalog-session.json"), MAX_CONTROL).unwrap();
        let envelope = &fixtures["valid-v1"];
        let payload: Value = serde_json::from_str(envelope["payload"].as_str().unwrap()).unwrap();
        let history = json!({"schema_version":1,"root_absolute":root,"fixture_id":"signed-catalog-v1","session_sha256":hash(&session_bytes),"receipts":[{"envelope_raw":serde_json::to_string(envelope).unwrap(),"payload_sha256":hash(envelope["payload"].as_str().unwrap().as_bytes()),"sequence":payload["sequence"],"accepted_at":now(),"time_basis":"system_clock","trusted_keys_before":{ROOT_KEY_ID:ROOT_KEY}}]});
        write_json(&root, &root.join("state/signed-catalog.json"), &history).unwrap();
        let policy = &fixtures["shell-self-copy-policy"];
        let proof = json!({"status":"trusted_fixture","production_update":false,"policy":serde_json::from_str::<Value>(policy["payload"].as_str().unwrap()).unwrap(),"policy_envelope_raw":serde_json::to_string(policy).unwrap(),"policy_payload_sha256":hash(policy["payload"].as_str().unwrap().as_bytes()),"session":session,"history":history,"old_sha256":asset.sha256,"candidate_sha256":asset.sha256,"bytes":asset.bytes});
        Self {
            root,
            tx,
            asset,
            proof,
        }
    }
    fn plan(&self) -> Plan {
        let mut plan = Plan {
            schema_version: 1,
            authorized_at: now(),
            root_absolute: self.root.clone(),
            current_relative: CURRENT.into(),
            candidate_relative: CANDIDATE.into(),
            asset: self.asset.clone(),
            controls: capture_controls(&self.root, true).unwrap(),
            trust_proof: self.proof.clone(),
            trial_mode: "normal".into(),
            plan_sha256: String::new(),
        };
        seal_plan(&mut plan).unwrap();
        plan
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        if self.root.parent() == Some(std::env::temp_dir().as_path())
            && self
                .root
                .file_name()
                .is_some_and(|n| n.to_string_lossy().starts_with("launcher-m5-"))
        {
            let _ = fs::remove_dir_all(&self.root);
        }
    }
}
#[test]
fn control_snapshot_restores_original_bytes_and_preserves_changed_files() {
    let f = Fixture::new();
    let snapshot = capture_controls(&f.root, true).unwrap();
    let original = fs::read(f.root.join("state/registry.json")).unwrap();
    save_controls(&f.root, &f.tx, &snapshot).unwrap();
    fs::write(f.root.join("state/registry.json"), b"{broken-current").unwrap();
    fs::write(f.root.join("state/unexpected.json"), b"new control").unwrap();
    assert!(verify_controls(&f.root, &snapshot).is_err());
    restore_controls(&f.root, &f.tx, &snapshot).unwrap();
    assert_eq!(
        fs::read(f.root.join("state/registry.json")).unwrap(),
        original
    );
    assert!(!f.root.join("state/unexpected.json").exists());
    assert_eq!(
        fs::read(f.tx.join("quarantine/state/unexpected.json")).unwrap(),
        b"new control"
    );
    restore_controls(&f.root, &f.tx, &snapshot).unwrap();
}
#[test]
fn unknown_schema_and_damaged_snapshot_refuse_without_overwrite() {
    let f = Fixture::new();
    let snapshot = capture_controls(&f.root, true).unwrap();
    save_controls(&f.root, &f.tx, &snapshot).unwrap();
    fs::write(
        f.root.join("state/registry.json"),
        b"{\"schema_version\":99}",
    )
    .unwrap();
    assert!(capture_controls(&f.root, true).is_err());
    fs::write(f.tx.join("controls/state/registry.json"), b"broken backup").unwrap();
    assert!(restore_controls(&f.root, &f.tx, &snapshot).is_err());
    assert_eq!(
        fs::read(f.root.join("state/registry.json")).unwrap(),
        b"{\"schema_version\":99}"
    );
}
#[test]
fn helper_rechecks_signed_policy_fixed_roots_and_backup_trust() {
    let f = Fixture::new();
    verify_fixture_proof(&f.root, &f.proof, &f.asset).unwrap();
    let plan = f.plan();
    save_controls(&f.root, &f.tx, &plan.controls).unwrap();
    let mut intent = Intent {
        schema_version: 1,
        transaction: "shell-update-fixture".into(),
        status: "trial".into(),
        plan,
        parent: ProcessIdentity {
            pid: 1,
            created_at: 1,
        },
        helper: None,
        trial: None,
        old_shell: f.asset.clone(),
        updated_at: now(),
        failure: None,
        intent_sha256: String::new(),
    };
    store_intent(&f.tx, &mut intent).unwrap();
    fs::write(
        f.root.join("state/signed-catalog-session.json"),
        b"broken trial write",
    )
    .unwrap();
    assert!(verify_fixture_proof(&f.root, &f.proof, &f.asset).is_err());
    assert!(load_intent(&f.tx).is_ok());
    restore_controls(&f.root, &f.tx, &intent.plan.controls).unwrap();
    let mut malicious = f.proof.clone();
    malicious["candidate_sha256"] = "a".repeat(64).into();
    assert!(verify_fixture_proof(&f.root, &malicious, &f.asset).is_err());
    let mut envelope: Value =
        serde_json::from_str(malicious["policy_envelope_raw"].as_str().unwrap()).unwrap();
    envelope["signature_hex"] = "0".repeat(128).into();
    malicious["policy_envelope_raw"] = serde_json::to_string(&envelope).unwrap().into();
    assert!(verify_fixture_proof(&f.root, &malicious, &f.asset).is_err());
}
#[test]
fn handshake_needs_exact_token_process_creation_and_both_ui_checks() {
    let req = TrialRequest {
        schema_version: 1,
        root_absolute: PathBuf::new(),
        transaction: "shell-update-fixture".into(),
        token: "a".repeat(64),
        expected_shell_sha256: "b".repeat(64),
        helper_pid: 1,
        helper_created_at: 2,
        timeout_ms: 30_000,
        trial_mode: "normal".into(),
    };
    let child = ProcessIdentity {
        pid: 10,
        created_at: 1234,
    };
    let mut ack = TrialAck {
        schema_version: 1,
        transaction: req.transaction.clone(),
        token: req.token.clone(),
        trial_pid: child.pid,
        trial_created_at: child.created_at,
        rendered: true,
        recovery_available: true,
        expected_shell_sha256: req.expected_shell_sha256.clone(),
    };
    ack_valid(&ack, &req, &child).unwrap();
    ack.trial_created_at += 1;
    assert!(ack_valid(&ack, &req, &child).is_err());
    ack.trial_created_at = child.created_at;
    ack.token = "bad".into();
    assert!(ack_valid(&ack, &req, &child).is_err());
    ack.token = req.token.clone();
    ack.recovery_available = false;
    assert!(ack_valid(&ack, &req, &child).is_err());
}
