import logging
import os
import re
import shlex
import shutil
import subprocess

debug = True

logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)


class CallData:
    def __init__(self, function_hash, function_arguments):
        assert function_hash is None or 0 <= function_hash <= 0xffffffff, "function hash must be 4 bytes long"
        self.function_hash = function_hash
        self.function_arguments = function_arguments

    def format(self):
        function_hash = hex(self.function_hash)[2:].zfill(8) if self.function_hash else ""
        return function_hash + "".join(hex(arg)[2:].zfill(32) for arg in self.function_arguments)


class Benchmark:
    def __init__(self, file, calls, osiris_path="./osiris/osiris.py", sguard_folder="./sGuard/"):
        self.file = file
        self.calls = calls
        self.osiris_path = osiris_path
        self.sguard_folder = sguard_folder

    def get_osiris_command(self, optimize=False):
        # TODO: we assume a Solidity file for now
        inputs = " ".join(calldata.format() for calldata in self.calls)

        is_solidity = self.file.endswith(".sol")
        is_evm = self.file.endswith(".evm")

        assert is_solidity or is_evm, "unknown test file"

        evm_flag = "--bytecode" if is_evm else ""

        cmd = f"python {self.osiris_path} -s {self.file} {evm_flag} {'--solidity-optimize' if optimize else ''} --repair --repair-input {inputs}"
        logging.debug(cmd)
        return cmd

    def execute_sguard(self, optimize=False):
        init_cwd = os.getcwd()
        sguard_read_target = os.path.abspath(os.path.join(self.sguard_folder, "contracts", "sample.sol"))
        sguard_write_target = os.path.abspath(os.path.join(self.sguard_folder, "contracts", "fixed.sol"))

        logging.debug(sguard_read_target)
        logging.debug(sguard_write_target)

        shutil.copyfile(self.file, sguard_read_target)

        # cleanup sGuard directory
        try:
            os.remove(sguard_write_target)
        except FileNotFoundError:
            pass

        # Run sguard
        os.chdir(self.sguard_folder)
        logging.debug(os.getcwd())
        process = subprocess.Popen(shlex.split("npm run dev"),
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
        logging.debug(process.communicate())

        os.chdir(init_cwd)
        logging.debug(os.getcwd())

        shutil.copyfile(sguard_write_target, self.file + ".sguard.fixed")

        # Recompile sguard output
        process = subprocess.Popen(shlex.split(f"solc {'--optimize' if optimize else ''} --bin-runtime {sguard_write_target}"),
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
        full_output = process.communicate()
        logging.debug(full_output)
        output = full_output[0].decode()

        bytecode = re.search(r"Binary of the runtime part:\s+([a-fA-F0-9]+)", output).group(1)

        logging.debug(bytecode)

        outputs = []

        # Run compiled code
        for calldata in self.calls:
            process = subprocess.Popen(shlex.split(f"evm --statdump --code {bytecode} --input {calldata.format()} run"),
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT)
            outputs.append(process.communicate()[0].decode())

        logging.debug(outputs)

        return outputs

    def execute_benchmarks(self):
        results = self.execute()
        optimized_results = [{k + "_optimized": v for k, v in res.items()} for res in self.execute(optimize=True)]

        return [{**result, **optimized_result} for result, optimized_result in zip(results, optimized_results)]

    def execute(self, optimize=False):
        # Execute Osiris tool
        osiris_command = self.get_osiris_command(optimize)
        process = subprocess.Popen(shlex.split(osiris_command),
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
        output = process.communicate()[0].decode()

        logging.debug("=== Osiris ===")
        logging.debug(output)

        # Execute sGuard
        sguard_outputs = self.execute_sguard(optimize)

        return self.parse_results(output, sguard_outputs)

    def parse_results(self, output, sguard_outputs):

        results = []
        i = 0

        while True:
            match = re.search("Benchmark for input ([a-fA-F\d]+\.+)", output)

            if not match:
                break

            contract_input = match.group(1)
            output = output[match.end():]
            sguard_output = sguard_outputs[i]

            data = {
                "function_hash": "0x" + contract_input,
                "original_gas_cost": int(re.search(r"Original call gas cost: (\d+)", output).group(1)),
                "repaired_gas_cost": int(re.search(r"Repaired call gas cost: (\d+)", output).group(1)),
                "sguard_gas_cost": int(re.search(r"gas used:\s+(\d+)", sguard_output).group(1)),
            }

            results.append(data)

            i += 1

        return results

    def pprint_results(self, results):
        def pprint_batch(result, original_key, repaired_key, sguard_key):
            original_cost = result[original_key]
            repaired_cost = result[repaired_key]
            sguard_cost = result[sguard_key]
            diff = repaired_cost - original_cost
            increase = diff / original_cost * 100

            sguard_diff = -(repaired_cost - sguard_cost)
            sguard_deacrease = sguard_diff / sguard_cost * 100
            print(f"\t  └> original gas cost:            {original_cost}")
            print(f"\t  └> Osiris repaired gas cost:     {repaired_cost}")
            print(f"\t  └> sGuard repaired gas cost:     {sguard_cost}")
            print(f"\t  └> increase vs. original cost:   {diff} ({increase:.1f}%)")
            print(f"\t  └> decrease vs sGuard cost:      {sguard_diff} ({sguard_deacrease:.1f}%)")

        print(self.file)
        for result in results:
            print(f"\t- {result['function_hash']}")
            pprint_batch(result, 'original_gas_cost', 'repaired_gas_cost', 'sguard_gas_cost')
            print(f"\t  |")
            print(f"\t  └> With solc --optimize:")
            pprint_batch(result, 'original_gas_cost_optimized', 'repaired_gas_cost_optimized', 'sguard_gas_cost_optimized')


benchmarks = [
    Benchmark("./benchmarks/addition.sol",
              [
                  CallData(0xab3ae255, [42]),  # transfer1(0, 42)
              ]),
    Benchmark("./benchmarks/multiplication.sol",
              [
                  CallData(0xab3ae255, [42]),  # transfer1(0, 42)
              ]),
    Benchmark("./benchmarks/subtraction.sol",
              [
                  CallData(0xab3ae255, [42]),  # transfer1(0, 42)
              ]),
#    Benchmark("./tests/AdditionSubtraction.sol",
#              [
#                  CallData(0x09921939, [0, 42]),  # transfer1(0, 42)
#              ]),
#    Benchmark("./tests/SimpleMultiplication.sol",
#              [
#                  CallData(0x399ae724, [0, 42]),  # init(0, 42)
#                  CallData(0x8fefd8ea, [1015, 42]),  # check(1015, 42)
#              ]),
#    Benchmark("./tests/SimpleAddition.sol",
#              [
#                  CallData(0x399ae724, [0, 42]),  # init(0, 42)
#                  CallData(0x8fefd8ea, [1015, 42]),  # check(1015, 42)
#              ]),
#    Benchmark("./tests/SimpleSubtraction.sol",
#              [
#                  # CallData(0x399ae724, [42, 42]),  # init(0, 42)   # remove because of bug in Solidity?
#                  CallData(0x8fefd8ea, [1015, 42]),  # check(1015, 42)
#              ]),
#    Benchmark("./tests/DummyAddition.evm",
#              [
#                  CallData(None, [42, 42]),
#              ]),
#    Benchmark("./tests/DummySubtraction.evm",
#              [
#                  CallData(None, [0, 0]),
#              ]),
#    Benchmark("./tests/DummyMultiplication.evm",
#              [
#                  CallData(None, [0, 1]),
#              ]),
#    Benchmark("./tests/DummyDivision.evm",
#              [
#                  CallData(None, [42, 42]),
#              ]),
#    Benchmark("./tests/DummyModulo.evm",
#              [
#                  CallData(None, [42, 42]),
#              ]),
]

if __name__ == "__main__":
    for benchmark in benchmarks:
        results = benchmark.execute_benchmarks()
        benchmark.pprint_results(results)
