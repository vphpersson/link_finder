from logging import getLogger
from dataclasses import dataclass
from re import search as re_search

from esprima import parseScript as esprima_parse_script
from esprima.nodes import Node as EsprimaNode
from esprima import Error as EsprimaError

LOG = getLogger(__name__)
ENDPOINT_CANDIDATE_PATTERN = r'(?<!application)(?<!text)(?<!<)\s*/\s*(?!>)'


@dataclass
class EndpointCandidateMatch:
    value: str
    context: str


CONTEXT_NODE_TYPES = {
    'AssignmentExpression',
    'VariableDeclarator',
    'Property',
    # 'BinaryExpression',
    'CallExpression',
    'NewExpression',
    'ReturnStatement',
    'ThrowStatement',
    'ExpressionStatement',
    'IfStatement'
}


def is_url_string_node(node: EsprimaNode) -> bool:

    if node.type == 'Literal':
        value = node.value
    elif node.type == 'TemplateElement':
        # TODO: Not sure about difference between the `cooked` and `raw` fields.
        value = node.value.cooked
    else:
        return False

    return isinstance(value, str) and re_search(pattern=ENDPOINT_CANDIDATE_PATTERN, string=value)


def find_endpoint_candidates(content: str, color_context: bool = True) -> list[EndpointCandidateMatch]:
    """Find endpoint candidates in the contents of a file."""

    node_to_metadata = dict()

    def delegate(node, metadata):
        node_to_metadata[node] = metadata

    program_tree = esprima_parse_script(code=content, options=dict(comment=True), delegate=delegate)

    context_node_stack: list[EsprimaNode] = []
    matches: list[EndpointCandidateMatch] = []

    def traverse(node):

        if not isinstance(node, EsprimaNode):
            return

        is_context_node = node.type in CONTEXT_NODE_TYPES

        if is_context_node:
            context_node_stack.append(node)

        if is_url_string_node(node):
            context_node: EsprimaNode = context_node_stack[-1]
            if context_node.type == 'IfStatement':
                context_node: EsprimaNode = context_node.test

            context_node_metadata = node_to_metadata[context_node]
            string_literal_metadata = node_to_metadata[node]

            endpoint_candidate: str = content[string_literal_metadata.start.offset:string_literal_metadata.end.offset]

            matches.append(
                EndpointCandidateMatch(
                    value=endpoint_candidate,
                    context=''.join([
                        content[context_node_metadata.start.offset:string_literal_metadata.start.offset],
                        ('\x1b[31m' if color_context else ''),
                        endpoint_candidate,
                        ('\x1b[0m' if color_context else ''),
                        content[string_literal_metadata.end.offset:context_node_metadata.end.offset]
                    ])
                )
            )

        else:
            for node_value in node.__dict__.values():
                if isinstance(node_value, list):
                    for element in node_value:
                        traverse(element)
                else:
                    traverse(node_value)

        if is_context_node:
            context_node_stack.pop()

    for base_node in program_tree.body:
        traverse(node=base_node)

    for comment in program_tree.comments:

        if comment.type == 'Line':
            comment_lines = [comment.value]
        elif comment.type == 'Block':
            comment_lines = comment.value.splitlines()
        else:
            raise ValueError('Bad comment type.')

        for comment_line in comment_lines:
            try:
                # Attempt to parse the comment as JavaScript code, extracting the string value and context as usual.
                parse_script_options = dict(code=comment_line, options=dict(tolerant=True), delegate=delegate)
                for base_node in esprima_parse_script(**parse_script_options).body:
                    content = comment_line
                    traverse(node=base_node)
            except EsprimaError:
                # In case the comment cannot be parsed as JavaScript code, perform a regex check (entailing no context).
                if re_search(pattern=ENDPOINT_CANDIDATE_PATTERN, string=comment_line):
                    matches.append(EndpointCandidateMatch(value=comment_line.lstrip(), context=comment_line))

    return matches
