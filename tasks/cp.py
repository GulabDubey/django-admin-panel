# Competitive Programming Questions:
class CompetitiveProgramming:
    @staticmethod
    def sumOfDigits(value: str)->int:
        return sum(map(int, value))
        
    def checkPalindrome(value: int)->bool:
        return value == value[::-1]

    def checkFactorial(value: int)->int:
        if value == 1:
            return 1
        return value * CompetitiveProgramming.checkFactorial(value-1)

#Task: let say, you have to take an input from user like "424323535254767"
# and you have to figure out if the number is even +2 else +1
# also add option to to quit/exit if the user do not want to continue

if __name__ == "__main__":
   while True:
    print("Enter a value? OR (exit/quit to stop)")
    n = input()
    if n in  ['exit', 'quit']:
        break
    print(f"Sum of {n} is: {CompetitiveProgramming.sumOfDigits(n)}")
    print(f"Is {n} a palindrome? {CompetitiveProgramming.checkPalindrome(n)}")
    print(f"Factorial of {int(n)} is: {CompetitiveProgramming.checkFactorial(int(n))}")

    