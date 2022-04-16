import logging
import re
import shlex
import subprocess

debug = False

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

    def get_command(self):
        # TODO: we assume a Solidity file for now
        inputs = " ".join(calldata.format() for calldata in self.calls)
        cmd = f"python {self.osiris_path} -s {self.file} --repair --repair-input {inputs}"
        logging.debug(cmd)
        return cmd

    def execute(self):
        command = self.get_command()
        process = subprocess.Popen(shlex.split(command),
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
        output = process.communicate()[0].decode()

        logging.debug(output)

        return self.parse_results(command, output)

    def parse_results(self, command, output):

        results = []

        while True:
            match = re.search("Benchmark for input ([a-fA-F\d]+\.+)", output)

            if not match:
                break

            contract_input = match.group(1)
            output = output[match.end():]

            data = {
                "function_hash": "0x" + contract_input,
                "original_gas_cost": int(re.search(r"Original call gas cost: (\d+)", output).group(1)),
                "repaired_gas_cost": int(re.search(r"Repaired call gas cost: (\d+)", output).group(1)),
            }

            results.append(data)

        return results

    def pprint_results(self, results):
        print(self.file)
        for result in results:
            original_cost = result['original_gas_cost']
            repaired_cost = result['repaired_gas_cost']
            diff = repaired_cost - original_cost
            increase = diff / original_cost * 100
            print(f"\t- {result['function_hash']}")
            print(f"\t  └> original gas cost:      {original_cost}")
            print(f"\t  └> repaired gas cost:      {repaired_cost}")
            print(f"\t  └> increased gas cost by:  {diff} ({increase:.1f}%)")


benchmarks = [
                 Benchmark("./tests/AdditionSubtraction.sol",
                           [
                               CallData(0x09921939, [0, 42]),  # transfer1(0, 42)
                           ]),
                 Benchmark("./tests/SimpleMultiplication.sol",
                           [
                               CallData(0x399ae724, [0, 42]),  # init(0, 42)
                               CallData(0x8fefd8ea, [1015, 42]),  # check(1015, 42)
                           ]),
                 Benchmark("./tests/SimpleAddition.sol",
                           [
                               CallData(0x399ae724, [0, 42]),  # init(0, 42)
                               CallData(0x8fefd8ea, [1015, 42]),  # check(1015, 42)
                           ]),
                 Benchmark("./tests/SimpleSubtraction.sol",
                           [
                               # CallData(0x399ae724, [42, 42]),  # init(0, 42)   # remove because of bug in Solidity?
                               CallData(0x8fefd8ea, [42, 42]),  # check(1015, 42)
                           ]),
             ]

if __name__ == "__main__":
    for benchmark in benchmarks:
        results = benchmark.execute()
        benchmark.pprint_results(results)
