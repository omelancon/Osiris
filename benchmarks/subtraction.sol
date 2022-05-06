contract Fund {
  mapping(address => uint) balances;
  uint counter = 0;
  uint dontFixMe = 0;

  function main(uint x) public {
    msg.sender.transfer(x - 1);
  }
}