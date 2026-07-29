#!/usr/bin/env python3

from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_a2_official_simulation as validator  # noqa: E402


POLICY_BYTES = b"fixture-a2-policy"
POLICY_SHA256 = hashlib.sha256(POLICY_BYTES).hexdigest()


class OfficialA2SimulationPreflightTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.rl = self.root / "unitree_rl_mjlab"
        self.mujoco = self.root / "unitree_mujoco"
        self.sdk2 = self.root / "unitree_sdk2"
        self._write_patched_fixture()

    @staticmethod
    def _write(path: Path, content: str | bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")

    @staticmethod
    def _model_xml(
        inertial: str = 'mass="2.5" diaginertia="0.2 0.3 0.4"',
    ) -> str:
        motors = "\n".join(
            f'<motor name="motor_{index}" joint="joint_{index}"/>'
            for index in range(12)
        )
        return f"""
        <mujoco>
          <worldbody>
            <body name="a2_p7_mount_link">
              <body name="p7_base_link">
                <inertial {inertial}/>
              </body>
            </body>
          </worldbody>
          <actuator>{motors}</actuator>
        </mujoco>
        """

    def _write_patched_fixture(self) -> None:
        self._write(
            self.rl / validator.A2_TYPES_PATH,
            """
            using LowCmd_t = unitree::robot::g1::publisher::LowCmd;
            using LowState_t = unitree::robot::g1::subscription::LowState;
            """,
        )
        self._write(
            self.rl / validator.VELOCITY_OBSERVATIONS_PATH,
            """
            REGISTER_OBSERVATION(velocity_commands)
            {
                return env->velocity_command_source->command();
            }
            """,
        )
        self._write(self.rl / validator.POLICY_PATH, POLICY_BYTES)

        self._write(self.rl / validator.A2_MODEL_PATH, self._model_xml())
        self._write(self.rl / validator.A2_SCENE_MODEL_PATH, self._model_xml())
        self._write(
            self.rl / validator.SIMULATOR_MAIN_PATH,
            """
            void *UnitreeSdk2BridgeThread(void *arg)
            {
                if (param::config.robot == "a2") {
                    interface = std::make_unique<G1Bridge>(model, data);
                } else if (param::config.robot == "go2") {
                    interface = std::make_unique<Go2Bridge>(model, data);
                }
            }
            """,
        )
        self._write(
            self.rl / validator.SIMULATOR_BRIDGE_PATH,
            """
            if (param::config.robot == "a2") {
                g1_lowstate->msg_.mode_machine() = 1;
            }
            """,
        )
        self._write(
            self.sdk2 / validator.SDK2_G1_PUBLISHER_PATH,
            """
            class LowCmd : public RealTimePublisher<unitree_hg::msg::dds_::LowCmd_> {
                const char* topic = "rt/lowcmd";
            };
            class LowState : public RealTimePublisher<unitree_hg::msg::dds_::LowState_> {
                const char* topic = "rt/lowstate";
            };
            """,
        )
        self._write(
            self.sdk2 / validator.SDK2_G1_SUBSCRIBER_PATH,
            """
            class LowCmd : public SubscriptionBase<unitree_hg::msg::dds_::LowCmd_> {
                const char* topic = "rt/lowcmd";
            };
            class LowState : public SubscriptionBase<unitree_hg::msg::dds_::LowState_> {
                const char* topic = "rt/lowstate";
            };
            """,
        )

    def _git_inspector(self, path: Path) -> validator.GitState:
        expected = {
            self.rl.resolve(): validator.PINNED_HEADS["unitree_rl_mjlab"],
            self.mujoco.resolve(): validator.PINNED_HEADS["unitree_mujoco"],
            self.sdk2.resolve(): validator.PINNED_HEADS["unitree_sdk2"],
        }
        resolved = path.resolve()
        return validator.GitState(resolved, expected[resolved])

    def _validate(self, **kwargs):
        return validator.validate_checkouts(
            self.rl,
            self.mujoco,
            self.sdk2,
            policy_sha256=POLICY_SHA256,
            git_inspector=self._git_inspector,
            **kwargs,
        )

    def test_patched_sources_and_pinned_policy_are_ready(self):
        report = self._validate()

        self.assertTrue(report["ready"])
        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["failed_checks"], [])
        self.assertEqual(report["summary"]["failed"], 0)
        self.assertEqual(report["scope"], "static_source_contract_only")
        self.assertIs(report["is_runtime_validation"], False)
        self.assertIs(report["is_gait_validation"], False)
        self.assertIs(report["safe_for_real_robot"], False)
        self.assertEqual(
            report["command_validation"],
            {
                "scope": "static_source_routing_only",
                "watchdog_verified": False,
                "limits_verified": False,
                "rearm_verified": False,
                "ros_bridge_verified": False,
            },
        )

    def test_original_motor_dispatch_mode_and_joystick_contract_fail_closed(self):
        self._write(
            self.rl / validator.SIMULATOR_MAIN_PATH,
            """
            #define NUM_MOTOR_IDL_GO 20
            void *UnitreeSdk2BridgeThread(void *arg)
            {
                if (m->nu > NUM_MOTOR_IDL_GO) {
                    interface = std::make_unique<G1Bridge>(m, d);
                } else {
                    interface = std::make_unique<Go2Bridge>(m, d);
                }
            }
            """,
        )
        self._write(
            self.rl / validator.SIMULATOR_BRIDGE_PATH,
            """
            if (param::config.robot.find("g1") != std::string::npos) {
                g1_lowstate->msg_.mode_machine() = 5;
            }
            """,
        )
        self._write(
            self.rl / validator.VELOCITY_OBSERVATIONS_PATH,
            """
            REGISTER_OBSERVATION(velocity_commands)
            {
                auto & joystick = env->robot->data.joystick;
                return {joystick->ly(), -joystick->lx(), -joystick->rx()};
            }
            """,
        )

        report = self._validate()

        self.assertFalse(report["ready"])
        self.assertEqual(report["status"], "failed")
        self.assertIn("bridge.no_motor_count_dispatch", report["failed_checks"])
        self.assertIn("bridge.a2_uses_g1_hg", report["failed_checks"])
        self.assertIn("bridge.a2_mode_machine", report["failed_checks"])
        self.assertIn("command.velocity_source", report["failed_checks"])

    def test_missing_policy_and_unpinned_default_both_fail(self):
        (self.rl / validator.POLICY_PATH).unlink()

        report = validator.validate_checkouts(
            self.rl,
            self.mujoco,
            self.sdk2,
            git_inspector=self._git_inspector,
        )

        self.assertFalse(report["ready"])
        self.assertIn("policy.exists", report["failed_checks"])
        self.assertIn("policy.sha256", report["failed_checks"])

    def test_wrong_policy_digest_fails(self):
        report = validator.validate_checkouts(
            self.rl,
            self.mujoco,
            self.sdk2,
            policy_sha256="0" * 64,
            git_inspector=self._git_inspector,
        )

        self.assertFalse(report["ready"])
        self.assertIn("policy.sha256", report["failed_checks"])
        self.assertEqual(report["policy"]["sha256"], POLICY_SHA256)

    def test_wrong_dds_family_and_motor_count_fail(self):
        self._write(
            self.rl / validator.A2_TYPES_PATH,
            """
            using LowCmd_t = unitree::robot::go2::publisher::LowCmd;
            using LowState_t = unitree::robot::go2::subscription::LowState;
            """,
        )
        self._write(
            self.sdk2 / validator.SDK2_G1_SUBSCRIBER_PATH,
            """
            class LowCmd : public SubscriptionBase<unitree_go::msg::dds_::LowCmd_> {
                const char* topic = "rt/lowcmd";
            };
            class LowState : public SubscriptionBase<unitree_go::msg::dds_::LowState_> {
                const char* topic = "rt/lowstate";
            };
            """,
        )
        motors = "".join(
            f'<motor name="motor_{index}" joint="joint_{index}"/>'
            for index in range(11)
        )
        self._write(
            self.rl / validator.A2_MODEL_PATH,
            (
                "<mujoco><worldbody><body name=\"a2_p7_mount_link\">"
                "<body name=\"p7_base_link\"><inertial mass=\"2\" "
                "diaginertia=\"1 1 1\"/></body></body></worldbody>"
                f"<actuator>{motors}</actuator></mujoco>"
            ),
        )

        report = self._validate()

        self.assertFalse(report["ready"])
        self.assertIn("dds.a2_controller_uses_g1", report["failed_checks"])
        self.assertIn("dds.sdk2_g1_wrapper_is_hg", report["failed_checks"])
        self.assertIn("mujoco.a2_motor_count", report["failed_checks"])

    def test_explicit_unpinned_audit_mode_is_reported(self):
        report = validator.validate_checkouts(
            self.rl,
            self.mujoco,
            self.sdk2,
            allow_unpinned_policy=True,
            git_inspector=self._git_inspector,
        )

        self.assertFalse(report["ready"])
        self.assertEqual(report["status"], "audit_only")
        self.assertFalse(report["policy"]["sha256_pinned"])
        self.assertEqual(report["warnings"], ["policy SHA-256 is not pinned"])

    def test_unpinned_audit_status_is_preserved_when_another_check_fails(self):
        (self.rl / validator.SIMULATOR_MAIN_PATH).unlink()

        report = validator.validate_checkouts(
            self.rl,
            self.mujoco,
            self.sdk2,
            allow_unpinned_policy=True,
            git_inspector=self._git_inspector,
        )

        self.assertFalse(report["ready"])
        self.assertEqual(report["status"], "audit_only")
        self.assertIn("bridge.no_motor_count_dispatch", report["failed_checks"])

    def test_official_models_without_p7_payload_fail_closed(self):
        motors = "".join(
            f'<motor name="motor_{index}" joint="joint_{index}"/>'
            for index in range(12)
        )
        official_model = f"<mujoco><actuator>{motors}</actuator></mujoco>"
        self._write(self.rl / validator.A2_MODEL_PATH, official_model)
        self._write(self.rl / validator.A2_SCENE_MODEL_PATH, official_model)

        report = self._validate()

        self.assertFalse(report["ready"])
        self.assertIn("model.a2.p7_payload", report["failed_checks"])
        self.assertIn("model.scene_a2.p7_payload", report["failed_checks"])

    def test_p7_payload_accepts_positive_fullinertia(self):
        model = self._model_xml(
            'mass="2.5" fullinertia="0.2 0.3 0.4 0.01 0.02 0.03"'
        )
        self._write(self.rl / validator.A2_MODEL_PATH, model)
        self._write(self.rl / validator.A2_SCENE_MODEL_PATH, model)

        report = self._validate()

        self.assertTrue(report["ready"])
        self.assertNotIn("model.a2.p7_payload", report["failed_checks"])
        self.assertNotIn("model.scene_a2.p7_payload", report["failed_checks"])

    def test_p7_payload_rejects_nonpositive_or_ambiguous_inertia(self):
        invalid_inertials = (
            'mass="0" diaginertia="0.2 0.3 0.4"',
            'mass="nan" diaginertia="0.2 0.3 0.4"',
            'mass="2.5" diaginertia="0.2 0 0.4"',
            'mass="2.5" fullinertia="0.2 -0.3 0.4 0 0 0"',
            (
                'mass="2.5" diaginertia="0.2 0.3 0.4" '
                'fullinertia="0.2 0.3 0.4 0 0 0"'
            ),
        )
        for inertial in invalid_inertials:
            with self.subTest(inertial=inertial):
                self._write(
                    self.rl / validator.A2_MODEL_PATH,
                    self._model_xml(inertial),
                )

                report = self._validate()

                self.assertFalse(report["ready"])
                self.assertIn("model.a2.p7_payload", report["failed_checks"])

    def test_head_mismatch_fails(self):
        def wrong_head(path: Path) -> validator.GitState:
            state = self._git_inspector(path)
            if path.resolve() == self.sdk2.resolve():
                return validator.GitState(state.root, "f" * 40)
            return state

        report = validator.validate_checkouts(
            self.rl,
            self.mujoco,
            self.sdk2,
            policy_sha256=POLICY_SHA256,
            git_inspector=wrong_head,
        )

        self.assertFalse(report["ready"])
        self.assertIn("checkout.unitree_sdk2.head", report["failed_checks"])

    def test_cli_prints_structured_failure_and_returns_nonzero(self):
        (self.rl / validator.POLICY_PATH).unlink()
        original_inspector = validator.inspect_git_checkout
        validator.inspect_git_checkout = self._git_inspector
        self.addCleanup(
            setattr, validator, "inspect_git_checkout", original_inspector
        )
        output = io.StringIO()
        with redirect_stdout(output):
            return_code = validator.main(
                [
                    "--unitree-rl-mjlab",
                    str(self.rl),
                    "--unitree-mujoco",
                    str(self.mujoco),
                    "--unitree-sdk2",
                    str(self.sdk2),
                    "--policy-sha256",
                    POLICY_SHA256,
                ]
            )

        report = json.loads(output.getvalue())
        self.assertEqual(return_code, 1)
        self.assertIs(report["ready"], False)
        self.assertEqual(report["status"], "failed")
        self.assertIn("policy.exists", report["failed_checks"])

    def test_cli_unpinned_audit_returns_nonzero(self):
        original_inspector = validator.inspect_git_checkout
        validator.inspect_git_checkout = self._git_inspector
        self.addCleanup(
            setattr, validator, "inspect_git_checkout", original_inspector
        )
        output = io.StringIO()
        with redirect_stdout(output):
            return_code = validator.main(
                [
                    "--unitree-rl-mjlab",
                    str(self.rl),
                    "--unitree-mujoco",
                    str(self.mujoco),
                    "--unitree-sdk2",
                    str(self.sdk2),
                    "--allow-unpinned-policy",
                ]
            )

        report = json.loads(output.getvalue())
        self.assertEqual(return_code, 1)
        self.assertIs(report["ready"], False)
        self.assertEqual(report["status"], "audit_only")

    def test_exception_report_preserves_static_scope_and_audit_status(self):
        original_validate = validator.validate_checkouts

        def raise_unexpected_error(*args, **kwargs):
            raise RuntimeError("fixture validation error")

        validator.validate_checkouts = raise_unexpected_error
        self.addCleanup(
            setattr, validator, "validate_checkouts", original_validate
        )
        output = io.StringIO()
        with redirect_stdout(output):
            return_code = validator.main(
                [
                    "--unitree-rl-mjlab",
                    str(self.rl),
                    "--unitree-mujoco",
                    str(self.mujoco),
                    "--unitree-sdk2",
                    str(self.sdk2),
                    "--allow-unpinned-policy",
                ]
            )

        report = json.loads(output.getvalue())
        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "audit_only")
        self.assertEqual(report["scope"], "static_source_contract_only")
        self.assertIs(report["is_runtime_validation"], False)
        self.assertIs(report["is_gait_validation"], False)
        self.assertIs(report["safe_for_real_robot"], False)
        self.assertEqual(
            report["command_validation"],
            validator.COMMAND_VALIDATION_FIELDS,
        )


if __name__ == "__main__":
    unittest.main()
