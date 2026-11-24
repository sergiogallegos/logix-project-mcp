"""Extract inventory metadata from a full Logix project export."""

from collections.abc import Iterator
from typing import Literal, TypedDict
from xml.etree.ElementTree import Element

PROTECTION_ELEMENTS = {
    "EncodedData", "EncryptionInfo", "EncryptedContent", "EncryptedSegments", "EncryptedAOIContent",
}
XML_BOOLEANS = {"true": True, "false": False, "1": True, "0": False}


class NamedMetadata(TypedDict):
    name: str | None
    description: str | None


class ControllerMetadata(NamedMetadata):
    processor_type: str | None
    major_revision: str | None
    minor_revision: str | None


class TaskEvent(TypedDict):
    trigger: str | None
    tag: str | None
    timeout_enabled: bool | None


class TaskInventory(NamedMetadata):
    type: str | None
    task_class: str | None
    rate: str | None
    priority: str | None
    watchdog: str | None
    inhibited: bool | None
    disable_update_outputs: bool | None
    event: TaskEvent | None
    scheduled_programs: list[str | None]


class TagSummary(NamedMetadata):
    data_type: str | None


class TagInventory(TagSummary):
    scope: Literal["controller", "program"]
    qualified_name: str | None
    tag_type: str | None
    alias_for: str | None
    dimensions: str | None
    external_access: str | None


class RoutineSummary(TypedDict):
    name: str | None
    type: str | None


class RoutineInventory(RoutineSummary):
    qualified_name: str | None
    protected: bool


class ProgramInventory(NamedMetadata):
    type: str | None
    main_routine: str | None
    fault_routine: str | None
    disabled: bool | None
    child_programs: list[str | None]
    tags: list[TagInventory]
    routines: list[RoutineInventory]


class ModulePort(TypedDict):
    id: str | None
    address: str | None
    type: str | None
    upstream: bool | None


class ModuleInventory(NamedMetadata):
    catalog_number: str | None
    parent_module: str | None
    parent_port_id: str | None
    major_revision: str | None
    minor_revision: str | None
    inhibited: bool | None
    ports: list[ModulePort]


class DataTypeMember(NamedMetadata):
    data_type: str | None
    dimension: str | None
    hidden: bool | None
    target: str | None
    bit_number: str | None


class DataTypeInventory(NamedMetadata):
    family: str | None
    data_type_class: str | None
    members: list[DataTypeMember]


class InstructionParameter(NamedMetadata):
    data_type: str | None
    usage: str | None
    dimensions: str | None
    required: bool | None
    visible: bool | None
    external_access: str | None


class InstructionInventory(NamedMetadata):
    revision: str | None
    revision_extension: str | None
    vendor: str | None
    protected: bool
    parameters: list[InstructionParameter]


class ProjectInventory(TypedDict):
    controller: ControllerMetadata
    tasks: list[TaskInventory]
    programs: list[ProgramInventory]
    controller_tags: list[TagInventory]
    modules: list[ModuleInventory]
    user_defined_types: list[DataTypeInventory]
    add_on_instructions: list[InstructionInventory]


def named_metadata(element: Element) -> NamedMetadata:
    return {"name": element.get("Name"), "description": element.findtext("Description")}


def xml_boolean(element: Element, attribute: str) -> bool | None:
    return XML_BOOLEANS.get(element.get(attribute, "").casefold())


def component_entries(parent: Element, container: str, kind: str) -> Iterator[Element]:
    for item in parent.findall(f"{container}/*"):
        if item.tag == kind or (item.tag == "EncodedData" and item.get("EncodedType") == kind):
            yield item


def has_protection(element: Element) -> bool:
    return xml_boolean(element, "IsEncrypted") is True or any(
        item.tag in PROTECTION_ELEMENTS for item in element.iter()
    )


def program_qualified_name(program: str | None, name: str | None) -> str | None:
    return f"Program:{program}.{name}" if program and name else None


def tag_summary(tag: Element) -> TagSummary:
    return {"name": tag.get("Name"), "data_type": tag.get("DataType"), "description": tag.findtext("Description")}


def routine_summary(routine: Element) -> RoutineSummary:
    return {"name": routine.get("Name"), "type": routine.get("Type")}


def tag_inventory(tag: Element, program: Element | None = None) -> TagInventory:
    summary = tag_summary(tag)
    name = summary["name"]
    return {
        **summary,
        "scope": "controller" if program is None else "program",
        "qualified_name": name if program is None else program_qualified_name(program.get("Name"), name),
        "tag_type": tag.get("TagType"),
        "alias_for": tag.get("AliasFor"),
        "dimensions": tag.get("Dimensions"),
        "external_access": tag.get("ExternalAccess"),
    }


def task_event(event: Element) -> TaskEvent:
    return {
        "trigger": event.get("EventTrigger"),
        "tag": event.get("EventTag"),
        "timeout_enabled": xml_boolean(event, "EnableTimeout"),
    }


def task_inventory(task: Element) -> TaskInventory:
    event = task.find("EventInfo")
    return {
        **named_metadata(task),
        "type": task.get("Type"),
        "task_class": task.get("Class"),
        "rate": task.get("Rate"),
        "priority": task.get("Priority"),
        "watchdog": task.get("Watchdog"),
        "inhibited": xml_boolean(task, "InhibitTask"),
        "disable_update_outputs": xml_boolean(task, "DisableUpdateOutputs"),
        "event": task_event(event) if event is not None else None,
        "scheduled_programs": [item.get("Name") for item in task.findall("ScheduledPrograms/ScheduledProgram")],
    }


def program_inventory(program: Element) -> ProgramInventory:
    name = program.get("Name")
    return {
        **named_metadata(program),
        "type": program.get("Type"),
        "main_routine": program.get("MainRoutineName"),
        "fault_routine": program.get("FaultRoutineName"),
        "disabled": xml_boolean(program, "Disabled"),
        "child_programs": [child.get("Name") for child in program.findall("ChildPrograms/ChildProgram")],
        "tags": [tag_inventory(tag, program) for tag in program.findall("Tags/Tag")],
        "routines": [
            {
                **routine_summary(routine),
                "qualified_name": program_qualified_name(name, routine.get("Name")),
                "protected": has_protection(routine),
            }
            for routine in component_entries(program, "Routines", "Routine")
        ],
    }


def module_inventory(module: Element) -> ModuleInventory:
    return {
        **named_metadata(module),
        "catalog_number": module.get("CatalogNumber"),
        "parent_module": module.get("ParentModule"),
        "parent_port_id": module.get("ParentModPortId"),
        "major_revision": module.get("Major"),
        "minor_revision": module.get("Minor"),
        "inhibited": xml_boolean(module, "Inhibited"),
        "ports": [
            {
                "id": port.get("Id"), "address": port.get("Address"), "type": port.get("Type"),
                "upstream": xml_boolean(port, "Upstream"),
            }
            for port in module.findall("Ports/Port")
        ],
    }


def data_type_inventory(data_type: Element) -> DataTypeInventory:
    return {
        **named_metadata(data_type),
        "family": data_type.get("Family"),
        "data_type_class": data_type.get("Class"),
        "members": [
            {
                **named_metadata(member),
                "data_type": member.get("DataType"),
                "dimension": member.get("Dimension"),
                "hidden": xml_boolean(member, "Hidden"),
                "target": member.get("Target"),
                "bit_number": member.get("BitNumber"),
            }
            for member in data_type.findall("Members/Member")
        ],
    }


def instruction_inventory(instruction: Element) -> InstructionInventory:
    return {
        **named_metadata(instruction),
        "revision": instruction.get("Revision"),
        "revision_extension": instruction.get("RevisionExtension"),
        "vendor": instruction.get("Vendor"),
        "protected": has_protection(instruction),
        "parameters": [
            {
                **named_metadata(parameter),
                "data_type": parameter.get("DataType"),
                "usage": parameter.get("Usage"),
                "dimensions": parameter.get("Dimensions"),
                "required": xml_boolean(parameter, "Required"),
                "visible": xml_boolean(parameter, "Visible"),
                "external_access": parameter.get("ExternalAccess"),
            }
            for parameter in instruction.findall("Parameters/Parameter")
        ],
    }


def project_inventory(controller: Element) -> ProjectInventory:
    return {
        "controller": {
            **named_metadata(controller),
            "processor_type": controller.get("ProcessorType"),
            "major_revision": controller.get("MajorRev"),
            "minor_revision": controller.get("MinorRev"),
        },
        "tasks": [task_inventory(task) for task in controller.findall("Tasks/Task")],
        "programs": [program_inventory(program) for program in controller.findall("Programs/Program")],
        "controller_tags": [tag_inventory(tag) for tag in controller.findall("Tags/Tag")],
        "modules": [module_inventory(module) for module in controller.findall("Modules/Module")],
        "user_defined_types": [
            data_type_inventory(data_type)
            for data_type in controller.findall("DataTypes/DataType")
            if data_type.get("Class", "User").casefold() == "user"
        ],
        "add_on_instructions": [
            instruction_inventory(instruction)
            for instruction in component_entries(controller, "AddOnInstructionDefinitions", "AddOnInstructionDefinition")
        ],
    }
