import re

import basicblock
import opcodes
import utils
import re

REVERT_INSTRUCTIONS =    ["JUMPDEST", "PUSH1 0x00", "DUP1", "REVERT"]

ADD_WITH_OVERFLOW_FLAG = [           # stack
                                     # a b
                          "DUP1",    # a a b
                          "SWAP2",   # b a a
                          "ADD",     # sum a
                          "SWAP1",   # a sum
                          "DUP2",    # sum a sum
                          "LT",      # overflow sum
                         ]

SUB_WITH_UNDERFLOW_FLAG = [          # stack
                                     # a b
                          "DUP1",    # a a b
                          "SWAP2",   # b a a
                          "SWAP1",   # a b a
                          "SUB",     # diff a
                          "SWAP1",   # a diff
                          "DUP2",    # diff a diff
                          "GT",      # underflow diff
                         ]

MUL_WITH_OUTOFBOUND_FLAG = [
                                      # stack
                                      # a b
                           "DUP2",    # b a b
                           "DUP2",    # a b a b
                           "MUL",     # prod a b
                           "SWAP2",   # b a prod
                           "SWAP1",   # a b prod"
                           "DUP2",    # b a b prod"
                           "DUP4",    # prod b a b prod
                           "DIV",     # a? a b prod
                           "EQ",      # eq? b prod
                           "SWAP1",   # b eq? prod
                           "ISZERO",  # iszero eq prod
                           "OR",      # ok prod
                           "ISZERO",  # outofbound prod
]

DIV_WITH_DIVISION_BY_ZERO_FLAG = [
                                      # stack
                                      # a b
                           "DUP2",    # b a b
                           "SWAP1",   # a b b
                           "DIV",     # div b
                           "SWAP1",   # b div
                           "ISZERO",  # div-by-zero div
]

def split_block(block, vertices, edges):
    # Takes in a block with a JUMP in the middle and updates vertices and edges to split this block into two
    # The reason this code is somewhat messy is that the data structure used ot represent basic blocks used
    # starting position in bytecode as identifiers for blocks. This is not the best when we want to mutate the
    # blocks. Thus a lot of energy is put in keeping position-based identifiers working
    # Note that actual position are broken after this, but the call to "fix_jumps" sorts everything out

    instructions = block.get_instructions()
    for i, inst in enumerate(instructions):
        if inst in ("JUMP", "JUMPI"):
            break

    assert i < len(instructions) - 1, "split block without middle jump"

    new_block_instructions = instructions[i+1:]
    instructions[:] = instructions[:i+1]
    new_falls_to = block.get_start_address() + 1

    # Create new block with tail of existing block
    new_block = basicblock.BasicBlock.from_instruction_objects(new_falls_to,
                                                               block.get_block_type(),
                                                               new_block_instructions,
                                                               block.get_jump_target())
    vertices[new_falls_to] = new_block

    # Adjust existing block
    jump_destination = int(re.match(r"PUSH\d+ 0x([0-9a-fA-F]+)", inst.jump_offset_origin).group(1), 16)
    block.set_block_type("conditional" if inst == "JUMPI" else "unconditional")
    block.set_falls_to(new_falls_to)
    block.set_end_address(new_falls_to - 1)
    block.set_jump_target(jump_destination)

    # Adjust edges
    existing_block_start = block.get_start_address()
    edges[new_falls_to] = edges[existing_block_start]
    edges[existing_block_start] = [jump_destination]
    if inst == "JUMPI": edges[existing_block_start].append(new_falls_to)

    basicblock.fix_jumps(vertices, edges)

def repair(arithmetic_errors, vertices, edges):
    max_block_start = max(vertices)
    revert_block_index = max_block_start + len(vertices[max_block_start])
    revert_block = basicblock.BasicBlock.from_instructions(revert_block_index, "terminal", REVERT_INSTRUCTIONS)
    vertices[revert_block_index] = revert_block

    for error in arithmetic_errors:
        if not error['validated']:
            continue

        instruction = error["instruction"].instruction.newest
        block = instruction.block
        index = block.instruction_index(instruction)
        block_instructions = block.get_instructions()

        jump_to_revert_hex = hex(revert_block.get_start_address())[2:]
        if len(jump_to_revert_hex) % 2 == 1: jump_to_revert_hex = "0" + jump_to_revert_hex
        jump_kind = len(jump_to_revert_hex) // 2

        push_jump_offset_instruction = basicblock.InstructionWrapper(f"PUSH{jump_kind} 0x{jump_to_revert_hex}",
                                                                     block=block)
        jumpi_instruction = basicblock.InstructionWrapper("JUMPI", block=block)
        jumpi_instruction.jump_offset_origin = push_jump_offset_instruction

        if error["type"] == "Overflow":
            if instruction == "ADD":
                block_instructions[index:index+1] = [basicblock.InstructionWrapper(op, block=block)
                                                     for op in ADD_WITH_OVERFLOW_FLAG] \
                                                    + [push_jump_offset_instruction, jumpi_instruction]
                split_block(block, vertices, edges)
            elif instruction == "MUL":
                block_instructions[index:index + 1] = [basicblock.InstructionWrapper(op, block=block)
                                                       for op in MUL_WITH_OUTOFBOUND_FLAG] \
                                                      + [push_jump_offset_instruction, jumpi_instruction]
                split_block(block, vertices, edges)
        elif error["type"] == "Underflow":
            if instruction == "SUB":
                block_instructions[index:index+1] = [basicblock.InstructionWrapper(op, block=block)
                                                     for op in SUB_WITH_UNDERFLOW_FLAG] \
                                                    + [push_jump_offset_instruction, jumpi_instruction]
                split_block(block, vertices, edges)
        elif error["type"] == "Division":
            if instruction == "DIV":
                block_instructions[index:index + 1] = [basicblock.InstructionWrapper(op, block=block)
                                                       for op in DIV_WITH_DIVISION_BY_ZERO_FLAG] \
                                                      + [push_jump_offset_instruction, jumpi_instruction]
                split_block(block, vertices, edges)

def get_gas_cost(instructions, input):
    hex_code = opcodes.assembly_to_hex(instructions)
    command = f"evm --statdump --code {hex_code} --input {input} run"
    result = utils.run_command(command, keep_stderr=True)  # evm stat dump is sent to stderr

    gas = re.search(r"gas[^\d\n]*(\d+)", result).group(1)

    return int(gas)

