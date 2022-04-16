contract C {

    mapping (address => uint) public unsignedBalanceOf;
    mapping (address => int32) public signedBalanceOf;

    // Unsigned overflow/underflow
    function init(address _to, uint _value) {
        //require(unsignedBalanceOf[msg.sender] > _value);
        //require(unsignedBalanceOf[_to] + _value >= unsignedBalanceOf[_to] && unsignedBalanceOf[msg.sender] > _value);
        //require(unsignedBalanceOf[msg.sender] > _value && unsignedBalanceOf[_to] + _value >= unsignedBalanceOf[_to]);
        unsignedBalanceOf[_to] = _value - 10;
    }

    function check(uint _x1, uint _x2) {
        if (_x1 - _x2 < 42) {
            throw;
        } else {
            throw;
        }
    }
}
