contract Multiplication {

    function unsigned_multiplication(uint x, uint y) returns (uint r) {
      r = x * y;
      if (r < 42) { throw; }
    }
}
