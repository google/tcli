py_library(
    name = "tcli_lib",
    srcs = ["tcli.py"],
    deps = [
        ":clitable_lib",
        ":command_parser_lib",
        ":command_response_lib",
        ":inventory_lib",
        ":text_buffer_lib",
    ],
)

py_library(
    name = "inventory_lib",
    srcs = [
        "inventory_base.py",
        "inventory_csv.py",
    ],
)

py_library(
    name = "clitable_lib",
    srcs = [
        "textfsm/clitable.py",
    ],
    deps = [
        "textfsm_lib",
    ],
)

py_library(
    name = "command_parser_lib",
    srcs = [
        "command_parser.py",
    ],
    deps = [
    ],
)

py_library(
    name = "command_response_lib",
    srcs = [
        "command_response.py",
    ],
)

py_library(
    name = "text_buffer_lib",
    srcs = [
        "text_buffer.py",
    ],
    deps = [],
)

py_library(
    name = "textfsm_lib",
    srcs = [
        "textfsm/textfsm.py",
    ],
    deps = [],
)

py_test(
    name = "tcli_test",
    size = "small",
    srcs = ["tcli_test.py"],
    data = glob(
        ["testdata/*"],
        exclude_directories = 0,
    ),
    tags = ["smoke"],
    deps = [
        ":tcli_lib",
    ],
)

py_test(
    name = "inventory_csv_test",
    size = "small",
    srcs = ["inventory_csv_test.py"],
    tags = ["smoke"],
    deps = [
        ":inventory_lib",
    ],
)

py_test(
    name = "inventory_base_test",
    size = "small",
    srcs = [
        "inventory_base.py",
        "inventory_base_test.py",
    ],
    tags = ["smoke"],
)

py_test(
    name = "command_response_test",
    size = "small",
    srcs = [
        "command_response_test.py",
    ],
    tags = ["smoke"],
    deps = [
        ":command_response_lib",
    ],
)

py_test(
    name = "text_buffer_test",
    size = "small",
    srcs = ["text_buffer_test.py"],
    tags = ["smoke"],
    deps = [
        ":text_buffer_lib",
    ],
)

py_test(
    name = "command_parser_test",
    size = "small",
    srcs = [
        "command_parser_test.py",
    ],
    tags = ["smoke"],
    deps = [
        ":command_parser_lib",
    ],
)

py_test(
    name = "textfsm_test",
    size = "small",
    srcs = [
        "textfsm/textfsm_test.py",
    ],
    tags = ["smoke"],
    deps = [
        ":textfsm_lib",
    ],
)

py_test(
    name = "system_test",
    size = "small",
    srcs = [
        "system_test.py",
    ],
    data = glob(
        ["testdata/*"],
        exclude_directories = 0,
    ),
    tags = ["smoke"],
    deps = [
        ":tcli_lib",
    ],
)

test_suite(
    name = "smoke_tests",
    tags = ["smoke"],
    tests = [],
)

py_binary(
    name = "tcli",
    srcs = ["main.py"],
    data = glob(
        ["testdata/*"],
        exclude_directories = 0,
    ),
    main = "main.py",
    deps = [":tcli_lib"],
)

py_library(
    name = "textfsm/__init__",
    srcs = ["textfsm/__init__.py"],
)
