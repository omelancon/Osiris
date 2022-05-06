contract Fund {
  mapping(address => uint) balances;

  function main(uint x) public {
    uint value = x + 1;
    if (value < 10000) {
        msg.sender.transfer(value);
    }
  }
}