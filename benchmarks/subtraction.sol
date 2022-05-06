contract Fund {
  mapping(address => uint) balances;
  uint counter = 0;
  uint dontFixMe = 0;

  function main(uint x) public {
        uint value = x - 1;
    if (value < 10000) {
        msg.sender.transfer(value);
    }
  }
}