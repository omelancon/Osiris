contract Fund {
  mapping(address => uint) balances;

  function main(uint x) public {
    uint value = x + 1;
    if (value < 10000) {
        msg.sender.transfer(value);
    }

    uint value2 = x + 2;
    if (value2 < 10000) {
        msg.sender.transfer(value2);
    }

    uint value3 = x + 3;
    if (value3 < 10000) {
        msg.sender.transfer(value3);
    }
  }
}