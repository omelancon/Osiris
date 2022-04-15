import logging
import re
import shlex
import subprocess

debug = True

logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)

class CallData:
    def __init__(self, function_hash, function_arguments):
        assert 0 <= function_hash <= 0xffffffff, "function hash must be 4 bytes long"
        self.function_hash = function_hash
        self.function_arguments = function_arguments

    def format(self):
        function_hash = hex(self.function_hash)[2:].zfill(8) if self.function_hash else ""
        return function_hash + "".join(hex(arg)[2:].zfill(32) for arg in self.function_arguments)

class Benchmark:
    def __init__(self, file, calls, osiris_path="./osiris/osiris.py"):
        self.file = file
        self.calls = calls
        self.osiris_path = osiris_path

    def get_commands(self):
        # TODO: we assume a Solidity file for now
        for calldata in self.calls:
            yield f"python {self.osiris_path} -s {self.file} --repair --repair-input {calldata.format()}"

    def execute(self):
        for command in self.get_commands():
            process = subprocess.Popen(shlex.split(command),
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT)
            output = process.communicate()[0].decode()

            logging.debug(output)

            yield self.parse_result(command, output)

    def parse_result(self, command, output):
        return {
            "function_hash": "0x" + re.search(r"--repair-input (\d{8})", command).group(1),
            "original_gas_cost": int(re.search(r"Original call gas cost: (\d+)", output).group(1)),
            "repaired_gas_cost": int(re.search(r"Repaired call gas cost: (\d+)", output).group(1)),
        }

    def pprint_results(self, results):
        print(self.file)
        for result in results:
            original_cost = result['original_gas_cost']
            repaired_cost = result['repaired_gas_cost']
            increase = (repaired_cost - original_cost) / original_cost * 100
            print(f"\t- {result['function_hash']}")
            print(f"\t  └> original gas cost:      {original_cost}")
            print(f"\t  └> repaired gas cost:      {repaired_cost}")
            print(f"\t  └> increased gas cost by:  {increase:.1f}%")

benchmarks = [
    Benchmark("./tests/AdditionSubtraction.sol",
              [
                  CallData(0x09921939, [0, 42]),
              ]),
    Benchmark("./tests/SimpleMultiplication.sol",
              [
                  CallData(0x4e058a5a, [42, 42]),
              ])
]

if __name__ == "__main__":
    for benchmark in benchmarks:
        results = benchmark.execute()
        benchmark.pprint_results(results)

