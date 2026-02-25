"""ptest 契约管理模块 CLI"""

import json
from pathlib import Path

from ..utils import print_colored, get_colored_text
from .manager import ContractManager


def setup_contract_subparser(subparsers):
    setup_contract_subparser = subparsers.add_parser(
        "contract", help=get_colored_text("Manage API contracts", 96)
    )

    contract_subparsers = setup_contract_subparser.add_subparsers(
        dest="contract_action", help="Contract actions"
    )

    import_parser = contract_subparsers.add_parser(
        "import", help="Import an API contract"
    )
    import_parser.add_argument("source", help="Contract file path or URL")
    import_parser.add_argument("--name", "-n", help="Contract name (optional)")

    contract_subparsers.add_parser("list", help="List all contracts")

    show_parser = contract_subparsers.add_parser("show", help="Show contract details")
    show_parser.add_argument("name", help="Contract name")
    show_parser.add_argument("--endpoint", "-e", help="Filter by endpoint path")

    delete_parser = contract_subparsers.add_parser("delete", help="Delete a contract")
    delete_parser.add_argument("name", help="Contract name")

    generate_parser = contract_subparsers.add_parser(
        "generate-cases", help="Generate test cases from contract"
    )
    generate_parser.add_argument("name", help="Contract name")
    generate_parser.add_argument(
        "--output", "-o", help="Output directory for test cases"
    )

    validate_parser = contract_subparsers.add_parser(
        "validate", help="Validate response against contract"
    )
    validate_parser.add_argument("name", help="Contract name")
    validate_parser.add_argument(
        "--endpoint", "-e", required=True, help="Endpoint path"
    )
    validate_parser.add_argument("--method", "-m", default="GET", help="HTTP method")
    validate_parser.add_argument(
        "--status", "-s", type=int, required=True, help="Status code"
    )
    validate_parser.add_argument(
        "--response", "-r", required=True, help="Response JSON file"
    )

    return setup_contract_subparser


def handle_contract_command(args) -> bool:
    if not hasattr(args, "contract_action") or not args.contract_action:
        print_colored("✗ Please specify a contract action", 91)
        return False

    manager = ContractManager()

    handlers = {
        "import": lambda: _handle_import(args, manager),
        "list": lambda: _handle_list(manager),
        "show": lambda: _handle_show(args, manager),
        "delete": lambda: _handle_delete(args, manager),
        "generate-cases": lambda: _handle_generate_cases(args, manager),
        "validate": lambda: _handle_validate(args, manager),
    }

    handler = handlers.get(args.contract_action)
    if handler:
        return handler()

    return False


def _handle_import(args, manager) -> bool:
    try:
        print_colored(f"Importing contract from {args.source}...", 94)
        contract = manager.import_contract(args.source, args.name)
        print_colored(f"✓ Contract '{contract.name}' imported successfully", 92)
        print(f"  Title: {contract.title}")
        print(f"  Version: {contract.version}")
        print(f"  Endpoints: {len(contract.endpoints)}")
        return True
    except Exception as e:
        print_colored(f"✗ Failed to import contract: {e}", 91)
        return False


def _handle_list(manager) -> bool:
    contracts = manager.list_contracts()
    if not contracts:
        print_colored("No contracts found", 93)
        return True

    print_colored("Available contracts:", 96)
    for name in contracts:
        print(f"  • {name}")
    return True


def _handle_show(args, manager) -> bool:
    contract = manager.load_contract(args.name)
    if not contract:
        print_colored(f"✗ Contract not found: {args.name}", 91)
        return False

    print_colored(f"Contract: {contract.name}", 96)
    print(f"  Title: {contract.title}")
    print(f"  Version: {contract.version}")
    print(f"  Description: {contract.description}")
    print(f"  Base URL: {contract.base_url}")
    print()
    print_colored(f"Endpoints ({len(contract.endpoints)}):", 94)

    for ep in contract.endpoints:
        if args.endpoint and args.endpoint not in ep.path:
            continue
        print(f"  {ep.method} {ep.path}")
        if ep.summary:
            print(f"    {ep.summary}")
        if ep.responses:
            response_codes = ", ".join(ep.responses.keys())
            print(f"    Responses: {response_codes}")

    return True


def _handle_delete(args, manager) -> bool:
    if manager.delete_contract(args.name):
        print_colored(f"✓ Contract '{args.name}' deleted", 92)
        return True
    else:
        print_colored(f"✗ Contract not found: {args.name}", 91)
        return False


def _handle_generate_cases(args, manager) -> bool:
    cases = manager.generate_test_cases(args.name)
    if not cases:
        print_colored(f"✗ No cases generated or contract not found: {args.name}", 91)
        return False

    if args.output:
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        for case in cases:
            case_file = output_dir / f"{case['id']}.json"
            with open(case_file, "w", encoding="utf-8") as f:
                json.dump(case, f, ensure_ascii=False, indent=2)
        print_colored(f"✓ Generated {len(cases)} test cases to {args.output}", 92)
    else:
        print_colored(f"Generated {len(cases)} test cases:", 92)
        for case in cases:
            print(f"  • {case['id']}: {case['description']}")

    return True


def _handle_validate(args, manager) -> bool:
    try:
        with open(args.response, "r", encoding="utf-8") as f:
            response_body = json.load(f)
    except Exception as e:
        print_colored(f"✗ Failed to load response file: {e}", 91)
        return False

    passed, errors = manager.validate_response(
        args.name, args.endpoint, args.method, args.status, response_body
    )

    if passed:
        print_colored("✓ Response is valid", 92)
        return True
    else:
        print_colored("✗ Response validation failed:", 91)
        for error in errors:
            print(f"  • {error}")
        return False
