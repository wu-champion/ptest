"""ptest 数据生成模块 - CLI命令处理器"""

import json
from pathlib import Path

from ..utils import print_colored, get_colored_text
from .generator import DataGenerator, DataGenerationConfig, DataType, DataTemplate


def setup_data_subparser(subparsers):
    """设置 data 子命令"""
    data_parser = subparsers.add_parser(
        "data",
        help=get_colored_text("Generate test data", 96),
        description="Generate various types of test data using Faker",
    )

    data_subparsers = data_parser.add_subparsers(
        dest="data_action", help="Data generation actions"
    )

    # generate 子命令
    generate_parser = data_subparsers.add_parser("generate", help="Generate test data")
    generate_parser.add_argument(
        "type", help="Data type to generate (e.g., name, email, phone)"
    )
    generate_parser.add_argument(
        "--count",
        "-c",
        type=int,
        default=1,
        help="Number of items to generate (default: 1)",
    )
    generate_parser.add_argument(
        "--locale",
        "-l",
        default="zh_CN",
        help="Locale for data generation (default: zh_CN)",
    )
    generate_parser.add_argument(
        "--format",
        "-f",
        choices=["json", "yaml", "csv", "raw"],
        default="json",
        help="Output format (default: json)",
    )
    generate_parser.add_argument("--output", "-o", help="Output file path")
    generate_parser.add_argument(
        "--seed", type=int, help="Random seed for reproducible generation"
    )

    # template 子命令
    template_parser = data_subparsers.add_parser(
        "template", help="Manage data templates"
    )
    template_subparsers = template_parser.add_subparsers(
        dest="template_action", help="Template actions"
    )

    # template generate
    template_generate = template_subparsers.add_parser(
        "generate", help="Generate data from template"
    )
    template_generate.add_argument("name", help="Template name")
    template_generate.add_argument(
        "--count", "-c", type=int, default=1, help="Number of items to generate"
    )
    template_generate.add_argument("--output", "-o", help="Output file path")

    # template save
    template_save = template_subparsers.add_parser("save", help="Save a new template")
    template_save.add_argument("name", help="Template name")
    template_save.add_argument(
        "definition", help="Template definition (JSON string or file path)"
    )

    # template list
    template_subparsers.add_parser("list", help="List all templates")

    # types 子命令
    data_subparsers.add_parser("types", help="List supported data types")

    return data_parser


def handle_data_command(args):
    """处理 data 命令"""
    if not hasattr(args, "data_action") or not args.data_action:
        print_colored("✗ Please specify a data action (generate/template/types)", 91)
        return

    if args.data_action == "generate":
        _handle_generate(args)
    elif args.data_action == "template":
        _handle_template(args)
    elif args.data_action == "types":
        _handle_types()


def _handle_generate(args):
    """处理 generate 子命令"""
    try:
        # 验证数据类型
        try:
            DataType(args.type)
        except ValueError:
            print_colored(f"✗ Unknown data type: {args.type}", 91)
            print_colored("  Use 'ptest data types' to see supported types", 93)
            return

        # 创建生成器
        config = DataGenerationConfig(locale=args.locale, seed=args.seed)
        generator = DataGenerator(config)

        # 生成数据
        print_colored(f"Generating {args.count} item(s) of type '{args.type}'...", 94)
        result = generator.generate(
            data_type=args.type, count=args.count, format=args.format
        )

        # 输出结果
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                if isinstance(result, str):
                    f.write(result)
                else:
                    json.dump(result, f, ensure_ascii=False, indent=2)
            print_colored(f"✓ Data saved to: {args.output}", 92)
        else:
            print()
            print(result)
            print()

        print_colored(f"✓ Generated {args.count} item(s) successfully", 92)

    except Exception as e:
        print_colored(f"✗ Error generating data: {e}", 91)


def _handle_template(args):
    """处理 template 子命令"""
    if not hasattr(args, "template_action") or not args.template_action:
        print_colored("✗ Please specify a template action (generate/save/list)", 91)
        return

    template_manager = DataTemplate()

    if args.template_action == "generate":
        _handle_template_generate(args, template_manager)
    elif args.template_action == "save":
        _handle_template_save(args, template_manager)
    elif args.template_action == "list":
        _handle_template_list(template_manager)


def _handle_template_generate(args, template_manager):
    """从模板生成数据"""
    template = template_manager.load_template(args.name)
    if not template:
        print_colored(f"✗ Template not found: {args.name}", 91)
        return

    config = DataGenerationConfig()
    generator = DataGenerator(config)

    print_colored(f"Generating {args.count} item(s) from template '{args.name}'...", 94)
    results = generator.generate_from_template(template, count=args.count)

    output = json.dumps(results, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print_colored(f"✓ Data saved to: {args.output}", 92)
    else:
        print()
        print(output)
        print()

    print_colored(f"✓ Generated {args.count} item(s) successfully", 92)


def _handle_template_save(args, template_manager):
    """保存模板"""
    try:
        # 尝试解析JSON
        if Path(args.definition).exists():
            with open(args.definition, "r", encoding="utf-8") as f:
                template = json.load(f)
        else:
            template = json.loads(args.definition)

        template_manager.save_template(args.name, template)
        print_colored(f"✓ Template '{args.name}' saved successfully", 92)

    except json.JSONDecodeError as e:
        print_colored(f"✗ Invalid JSON: {e}", 91)
    except Exception as e:
        print_colored(f"✗ Error saving template: {e}", 91)


def _handle_template_list(template_manager):
    """列出所有模板"""
    templates = template_manager.list_templates()

    if not templates:
        print_colored("No templates found", 93)
        return

    print_colored("Available templates:", 96)
    for name in templates:
        print(f"  • {name}")


def _handle_types():
    """列出支持的数据类型"""
    generator = DataGenerator()
    types = generator.list_supported_types()

    print_colored("Supported data types:", 96)
    print()

    # 按类别分组
    categories = {
        "Basic": [
            "name",
            "chinese_name",
            "english_name",
            "phone",
            "email",
            "address",
            "id_card",
            "uuid",
        ],
        "Network": ["url", "ip", "ipv4", "ipv6", "domain", "mac_address"],
        "Business": ["company", "job", "username", "password", "credit_card"],
        "Time": ["date", "time", "datetime", "timestamp"],
        "Text": ["text", "sentence", "paragraph", "word"],
        "Numeric": ["integer", "float", "boolean"],
    }

    for category, type_list in categories.items():
        print_colored(f"{category}:", 94)
        for t in type_list:
            if t in types:
                print(f"  • {t}")
        print()

    print_colored(f"Total: {len(types)} types", 93)
