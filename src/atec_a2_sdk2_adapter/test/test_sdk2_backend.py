from types import SimpleNamespace

import pytest

from atec_a2_sdk2_adapter.sdk2_backend import (
    A2_SPORT_API_VERSION,
    CYCLONEDDS_VERSION,
    SDK2BackendError,
    SDK2_CRITICAL_FILE_SHA256,
    SDK2_PYTHON_COMMIT,
    SDK2_PYTHON_REPOSITORY,
    SDK2_PYTHON_VERSION,
    SPORT_STATE_TOPIC,
    UnitreeA2SportBackend,
    validate_wired_network_interface,
    verify_pinned_sdk2_installation,
)


TEST_BACKEND_OPTIONS = {
    "revision_verifier": lambda: None,
    "interface_validator": lambda _name: None,
}


def test_official_sdk_source_is_pinned():
    assert SDK2_PYTHON_REPOSITORY == (
        "https://github.com/unitreerobotics/unitree_sdk2_python"
    )
    assert SDK2_PYTHON_COMMIT == "65691c8a8bc53b98d3976dba4dbf9d5d20b2e7f5"


def test_installed_sdk_revision_metadata_must_match_the_pin():
    direct_url = (
        '{"url":"https://github.com/unitreerobotics/unitree_sdk2_python.git",'
        '"vcs_info":{"vcs":"git",'
        '"commit_id":"65691c8a8bc53b98d3976dba4dbf9d5d20b2e7f5"}}'
    )
    distribution = SimpleNamespace(
        read_text=lambda _name: direct_url,
        version=SDK2_PYTHON_VERSION,
        locate_file=lambda name: name,
    )
    verify_pinned_sdk2_installation(
        lambda _name: distribution,
        package_version_loader=lambda _name: CYCLONEDDS_VERSION,
        file_hasher=lambda path: SDK2_CRITICAL_FILE_SHA256[str(path)],
    )


@pytest.mark.parametrize(
    "direct_url",
    [
        None,
        "{}",
        (
            '{"url":"https://github.com/unitreerobotics/unitree_sdk2_python.git",'
            '"vcs_info":{"vcs":"git","commit_id":"wrong"}}'
        ),
        (
            '{"url":"https://github.com/example/fork",'
            '"vcs_info":{"vcs":"git",'
            '"commit_id":"65691c8a8bc53b98d3976dba4dbf9d5d20b2e7f5"}}'
        ),
    ],
)
def test_unverified_sdk_revision_metadata_is_rejected(direct_url):
    distribution = SimpleNamespace(
        read_text=lambda _name: direct_url,
        version=SDK2_PYTHON_VERSION,
    )
    with pytest.raises(SDK2BackendError):
        verify_pinned_sdk2_installation(lambda _name: distribution)


def verified_distribution():
    direct_url = (
        '{"url":"https://github.com/unitreerobotics/unitree_sdk2_python.git",'
        '"vcs_info":{"vcs":"git",'
        '"commit_id":"65691c8a8bc53b98d3976dba4dbf9d5d20b2e7f5"}}'
    )
    return SimpleNamespace(
        read_text=lambda _name: direct_url,
        version=SDK2_PYTHON_VERSION,
        locate_file=lambda name: name,
    )


def test_wrong_cyclonedds_version_is_rejected():
    with pytest.raises(SDK2BackendError, match="cyclonedds version"):
        verify_pinned_sdk2_installation(
            lambda _name: verified_distribution(),
            package_version_loader=lambda _name: "0.11.0",
        )


def test_modified_sdk_file_is_rejected():
    with pytest.raises(SDK2BackendError, match="file hash does not match"):
        verify_pinned_sdk2_installation(
            lambda _name: verified_distribution(),
            package_version_loader=lambda _name: CYCLONEDDS_VERSION,
            file_hasher=lambda _path: "0" * 64,
        )


class FakeSportClient:
    def __init__(self):
        self.calls = []

    def SetTimeout(self, timeout):
        self.calls.append(("SetTimeout", timeout))

    def Init(self):
        self.calls.append(("Init",))

    def GetServerApiVersion(self):
        self.calls.append(("GetServerApiVersion",))
        return 0, A2_SPORT_API_VERSION

    def Move(self, vx, vy, wz):
        self.calls.append(("Move", vx, vy, wz))
        return 0

    def StopMove(self):
        self.calls.append(("StopMove",))
        return 0


class FakeSubscriber:
    def __init__(self, topic, message_type):
        self.topic = topic
        self.message_type = message_type
        self.handler = None
        self.queue_length = None
        self.closed = False

    def Init(self, handler, queue_length):
        self.handler = handler
        self.queue_length = queue_length

    def Close(self):
        self.closed = True


def fake_modules():
    client = FakeSportClient()
    initialized = []
    subscribers = []

    def make_subscriber(topic, message_type):
        subscriber = FakeSubscriber(topic, message_type)
        subscribers.append(subscriber)
        return subscriber

    modules = {
        "unitree_sdk2py.core.channel": SimpleNamespace(
            ChannelFactoryInitialize=lambda domain, interface: initialized.append(
                (domain, interface)
            ),
            ChannelSubscriber=make_subscriber,
        ),
        "unitree_sdk2py.a2.sport.sport_client": SimpleNamespace(
            SportClient=lambda: client
        ),
        "unitree_sdk2py.idl.unitree_go.msg.dds_": SimpleNamespace(
            SportModeState_=object
        ),
    }
    loaded = []

    def loader(name):
        loaded.append(name)
        return modules[name]

    return client, initialized, subscribers, loaded, loader


def test_sdk_is_lazy_and_uses_only_a2_move_stop_interface():
    client, initialized, subscribers, loaded, loader = fake_modules()
    states = []
    backend = UnitreeA2SportBackend(
        "enp2s0",
        0,
        0.03,
        lambda error, mode: states.append((error, mode)),
        loader,
        **TEST_BACKEND_OPTIONS,
    )
    assert loaded == []

    backend.start()
    assert initialized == [(0, "enp2s0")]
    assert subscribers[0].topic == SPORT_STATE_TOPIC
    assert subscribers[0].queue_length == 0
    assert client.calls == [
        ("SetTimeout", 0.03),
        ("Init",),
        ("GetServerApiVersion",),
    ]

    assert backend.move(0.1, -0.2) == 0
    assert backend.stop() == 0
    assert client.calls[-2:] == [
        ("Move", 0.1, 0.0, -0.2),
        ("StopMove",),
    ]
    subscribers[0].handler(SimpleNamespace(error_code=0, mode=4))
    subscribers[0].handler(SimpleNamespace(mode=4))
    assert states == [(0, 4), (None, None)]

    backend.close()
    assert subscribers[0].closed


def test_network_interface_is_required_before_any_import():
    _, _, _, loaded, loader = fake_modules()
    backend = UnitreeA2SportBackend(
        "", 0, 0.03, lambda _e, _m: None, loader, **TEST_BACKEND_OPTIONS
    )
    with pytest.raises(SDK2BackendError, match="network_interface"):
        backend.start()
    assert loaded == []


def make_interface_sysfs(tmp_path, name="enp2s0", hardware_type=1, flags="0x1"):
    interface_path = tmp_path / name
    interface_path.mkdir()
    (interface_path / "type").write_text(str(hardware_type), encoding="ascii")
    (interface_path / "flags").write_text(flags, encoding="ascii")
    return interface_path


def test_wired_network_interface_validation_accepts_enabled_ethernet(tmp_path):
    make_interface_sysfs(tmp_path)
    validate_wired_network_interface(
        "enp2s0",
        interface_lookup=lambda _name: 2,
        sysfs_root=tmp_path,
    )


@pytest.mark.parametrize(
    ("hardware_type", "flags", "message"),
    [
        (772, "0x9", "wired Ethernet"),
        (1, "0x0", "not enabled"),
    ],
)
def test_non_ethernet_or_disabled_interface_is_rejected(
    tmp_path, hardware_type, flags, message
):
    make_interface_sysfs(
        tmp_path,
        hardware_type=hardware_type,
        flags=flags,
    )
    with pytest.raises(SDK2BackendError, match=message):
        validate_wired_network_interface(
            "enp2s0",
            interface_lookup=lambda _name: 2,
            sysfs_root=tmp_path,
        )


def test_wireless_interface_is_rejected(tmp_path):
    interface_path = make_interface_sysfs(tmp_path, name="wlp3s0")
    (interface_path / "wireless").mkdir()
    with pytest.raises(SDK2BackendError, match="must not be wireless"):
        validate_wired_network_interface(
            "wlp3s0",
            interface_lookup=lambda _name: 3,
            sysfs_root=tmp_path,
        )


def test_backend_cannot_start_twice():
    _, _, _, _, loader = fake_modules()
    backend = UnitreeA2SportBackend(
        "enp2s0",
        0,
        0.03,
        lambda _e, _m: None,
        loader,
        **TEST_BACKEND_OPTIONS,
    )
    backend.start()
    with pytest.raises(SDK2BackendError, match="already started"):
        backend.start()


def test_subscriber_init_failure_does_not_construct_command_client():
    _, initialized, _, _, base_loader = fake_modules()
    client_constructions = []

    class BrokenSubscriber(FakeSubscriber):
        def Init(self, handler, queue_length):
            raise RuntimeError("reader_failed")

    channel_module = SimpleNamespace(
        ChannelFactoryInitialize=lambda domain, interface: initialized.append(
            (domain, interface)
        ),
        ChannelSubscriber=BrokenSubscriber,
    )

    def loader(name):
        if name == "unitree_sdk2py.core.channel":
            return channel_module
        if name == "unitree_sdk2py.a2.sport.sport_client":
            return SimpleNamespace(
                SportClient=lambda: client_constructions.append(True)
            )
        return base_loader(name)

    backend = UnitreeA2SportBackend(
        "enp2s0",
        0,
        0.02,
        lambda _e, _m: None,
        loader,
        **TEST_BACKEND_OPTIONS,
    )
    with pytest.raises(SDK2BackendError, match="reader_failed"):
        backend.start()
    assert not client_constructions


def test_client_init_failure_closes_initialized_subscriber():
    _, initialized, subscribers, _, base_loader = fake_modules()

    class BrokenClient(FakeSportClient):
        def Init(self):
            raise RuntimeError("client_failed")

    def make_subscriber(topic, message_type):
        subscriber = FakeSubscriber(topic, message_type)
        subscribers.append(subscriber)
        return subscriber

    channel_module = SimpleNamespace(
        ChannelFactoryInitialize=lambda domain, interface: initialized.append(
            (domain, interface)
        ),
        ChannelSubscriber=make_subscriber,
    )

    def loader(name):
        if name == "unitree_sdk2py.core.channel":
            return channel_module
        if name == "unitree_sdk2py.a2.sport.sport_client":
            return SimpleNamespace(SportClient=BrokenClient)
        return base_loader(name)

    backend = UnitreeA2SportBackend(
        "enp2s0",
        0,
        0.02,
        lambda _e, _m: None,
        loader,
        **TEST_BACKEND_OPTIONS,
    )
    with pytest.raises(SDK2BackendError, match="client_failed"):
        backend.start()
    assert subscribers[0].closed
    assert not backend.started


@pytest.mark.parametrize(
    ("version_result", "message"),
    [
        ((3104, None), "version query failed"),
        ((0, "9.9.9"), "version does not match"),
    ],
)
def test_server_api_version_must_match_before_backend_starts(
    version_result, message
):
    _, initialized, subscribers, _, base_loader = fake_modules()

    class WrongVersionClient(FakeSportClient):
        def GetServerApiVersion(self):
            self.calls.append(("GetServerApiVersion",))
            return version_result

    def make_subscriber(topic, message_type):
        subscriber = FakeSubscriber(topic, message_type)
        subscribers.append(subscriber)
        return subscriber

    channel_module = SimpleNamespace(
        ChannelFactoryInitialize=lambda domain, interface: initialized.append(
            (domain, interface)
        ),
        ChannelSubscriber=make_subscriber,
    )

    def loader(name):
        if name == "unitree_sdk2py.core.channel":
            return channel_module
        if name == "unitree_sdk2py.a2.sport.sport_client":
            return SimpleNamespace(SportClient=WrongVersionClient)
        return base_loader(name)

    backend = UnitreeA2SportBackend(
        "enp2s0",
        0,
        0.02,
        lambda _e, _m: None,
        loader,
        **TEST_BACKEND_OPTIONS,
    )
    with pytest.raises(SDK2BackendError, match=message):
        backend.start()
    assert subscribers[0].closed
    assert not backend.started


def test_invalid_domain_or_missing_interface_is_rejected_before_imports():
    _, _, _, loaded, loader = fake_modules()
    invalid_domain = UnitreeA2SportBackend(
        "enp2s0",
        233,
        0.02,
        lambda _e, _m: None,
        loader,
        **TEST_BACKEND_OPTIONS,
    )
    with pytest.raises(SDK2BackendError, match="dds_domain_id"):
        invalid_domain.start()

    options = dict(TEST_BACKEND_OPTIONS)
    options["interface_validator"] = lambda name: validate_wired_network_interface(
        name,
        interface_lookup=lambda _name: (_ for _ in ()).throw(OSError("missing")),
    )
    missing_interface = UnitreeA2SportBackend(
        "missing0",
        0,
        0.02,
        lambda _e, _m: None,
        loader,
        **options,
    )
    with pytest.raises(SDK2BackendError, match="does not exist"):
        missing_interface.start()
    assert loaded == []
