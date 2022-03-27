import re

class InstructionWrapper(str):
    def __new__(cls, *args, **kwargs):
        return super().__new__(cls, *args)

    def __init__(self, *args, old=None):
        self._jump_offset_origin = None
        self.old = old
        super().__init__()

    @property
    def opcode(self):
        return self.split()[0]

    @property
    def jump_offset_origin(self):
        return self._jump_offset_origin

    @jump_offset_origin.setter
    def jump_offset_origin(self, val):
        if self._jump_offset_origin is None or self._jump_offset_origin == val:
            self._jump_offset_origin = val
        else:
            raise RuntimeError(f"multiple origins for {self}")


class BasicBlock:
    def __init__(self, start_address, end_address):
        self.start = start_address
        self.end = end_address
        self.instructions = []  # each instruction is a string
        self.jump_target = 0

    def __iter__(self):
        yield from self.get_instructions()

    def __len__(self):
        s = 0
        for inst in self:
            s += 1 + (get_push_instruction_kind(inst) or 0)
        return s

    def __bool__(self):
        return True

    def get_start_address(self):
        return self.start

    def set_start_address(self, address):
        self.start = address

    def get_end_address(self):
        return self.end

    def set_end_address(self, address):
        self.end = address

    def add_instruction(self, instruction):
        self.instructions.append(InstructionWrapper(instruction))

    def get_instructions(self):
        return self.instructions

    def set_block_type(self, type):
        self.type = type

    def get_block_type(self):
        return self.type

    def set_falls_to(self, address):
        self.falls_to = address

    def get_falls_to(self):
        return self.falls_to

    def set_jump_target(self, address):
        if isinstance(address, int):
            self.jump_target = address
        else:
            self.jump_target = -1

    def get_jump_target(self):
        return self.jump_target

    def set_branch_expression(self, branch):
        self.branch_expression = branch

    def get_branch_expression(self):
        return self.branch_expression

    def display(self):
        print("================")
        print("start address: %x" % self.start)
        print("end address: %x" % self.end)
        print("end statement type: " + self.type)
        for instr in self.instructions:
            print(instr)

def get_push_instruction_kind(inst):
    if inst.startswith("PUSH"):
        return int(re.match(r"PUSH(\d+)", inst).group(1))
    else:
        return None

def get_sorted_blocks(blocks):
    return sorted(blocks.values(), key=lambda b: b.get_start_address())

def bb_to_bytecode(blocks):
    return [inst for b in get_sorted_blocks(blocks) for inst in b]

def fix_push_location(block, instruction, value):
    assert instruction.startswith("PUSH")

    block_instructions = block.get_instructions()
    for i, block_inst in enumerate(block_instructions):
        if instruction is block_inst or block_inst.old is instruction:
            break
    else:
        raise ValueError("instruction '{instruction}' not in block")

    push_size = get_push_instruction_kind(instruction)
    initial_hex = instruction.split()[1][2:]
    new_hex = hex(value)[2:].rjust(push_size * 2, "0")

    if initial_hex == new_hex:
        # Do not replace is the offset is already correct
        # This may happen if multiple jumps try to fix the same push
        return False
    else:
        push_size = len(new_hex) // 2

        new_instruction = InstructionWrapper(f"PUSH{push_size} 0x{new_hex}", old=instruction)
        block_instructions[i] = new_instruction

    # Indicate whether the PUSH size changed and will require further adjustment of jump offsets
    return len(initial_hex) != len(new_hex)

def fix_jumps(blocks, edges):
    # Readjusts jump locations in the CFG after blocks were updated, ising instructions as source of truth
    # since jump locations and end are now wrong. We first adjust starting and end locations inside blocks,
    # then we use the edge map to adjust jump locations
    # NOTE: Fixes blocks and edges inplace

    new_blocks = {}
    new_edges = {}
    sorted_blocks = get_sorted_blocks(blocks)

    # Update locations
    offset = 0
    for block in sorted_blocks:
        # Recover old values
        block_len = len(block)

        # Write new values
        new_falls_to = offset + block_len

        block.set_start_address(offset)
        block.set_falls_to(new_falls_to)
        block.set_end_address(new_falls_to - 1)  # Is only valid because the last instruction is a JUMP, JUMPI or STOP

        new_blocks[offset] = block
        offset = new_falls_to

    # Update jumps
    block_length_has_changed = False

    for block in sorted_blocks:
        block_start = block.get_start_address()
        new_jump_target = blocks[block.get_jump_target()].start
        block.set_jump_target(new_jump_target)
        block_type = block.get_block_type()

        # Update jump instructions
        if block_type not in ("terminal", "falls_to"):
            instructions = block.get_instructions()
            jump_instruction = instructions[-1]

            assert jump_instruction in ("JUMP", "JUMPI"), "block does not end with JUMP"

            origin_instruction = jump_instruction.jump_offset_origin.origin_instruction
            origin_block = jump_instruction.jump_offset_origin.origin_block

            if not origin_instruction:
                raise RuntimeError("jump to dynamic location")

            block_length_has_changed = fix_push_location(origin_block, origin_instruction, new_jump_target) or block_length_has_changed


        # Add to edge map
        if block_type == "terminal":
            new_edges[block_start] = []
        elif block_type == "unconditional":
            new_edges[block_start] = [new_jump_target]
        elif block_type == "conditional":
            new_edges[block_start] = sorted([block.get_falls_to(), new_jump_target])
        elif block_type == "falls_to":
            new_edges[block_start] = [block.get_falls_to()]
        else:
            raise NotImplementedError(f"unknown block type '{block_type}'")

    # Mutate edges and blocks maps
    blocks.clear()
    blocks.update(new_blocks)

    edges.clear()
    edges.update(new_edges)

    # If size of a block changed when adjusting a push of a jump offset, repeat until a fixed point is reached
    if block_length_has_changed:
        fix_jumps(blocks, edges)



