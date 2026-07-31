#LIFO
class Stack:
    def __init__(self):
        self.__arr = []
    
    def push(self, data):
        self.__arr.append(data)

    def pop(self):
        return self.__arr.pop() if len(self.__arr) else "Empty stack!"

    def show(self):
        return self.__arr

#FIFO
class Queue:
    def __init__(self):
        self.__arr = []
    
    def enqueue(self, data):
        self.__arr.append(data)

    def dequeue(self):
        if not len(self.__arr): raise IndexError("Empty Queue!")
        self.__arr.pop(0) 

    def show(self):
        return self.__arr

class Node:
    def __init__(self, data):
        self._data = data
        self._next = None
        self._prev = None

class LList:
    def __init__(self):
        self.__head = None

    def insert_at_beg(self, data):
        node = Node(data)
        node._next = self.__head
        self.__head = node

    def insert_at_end(self, data):
        node = Node(data)
        
        if self.__head is None:
            self.__head = node
            return

        temp = self.__head
        while temp._next is not None:
            temp = temp._next
        
        temp._next = node

    def show(self):
        temp = self.__head

        while temp:
            print(temp._data, end="->")
            temp = temp._next

class DLList: 
    def __init__(self):
        self.__head = None


    def insert_at_beg(self, data):
        node = Node(data)
        
        if self.__head is None:
            self.__head = node
            return
        
        node._next = self.__head
        self.__head._prev = node
        self.__head = node
        
    def showForward(self):
        temp = self.__head

        if not temp:
            raise Exception("Empty List!")
        
        while temp:
            print(temp._data, end="<->")
            temp = temp._next

        print("None")

#circular-liniked list: head->next->tail->head
class CLList:
    def __init__(self):
        self.__head = None

    def insert_at_beg(self, data):
        node = Node(data)

        if self.__head is None:
            self.__head = node
            node._next = self.__head
            return
        
        temp = self.__head
        while temp._next != self.__head:
            temp = temp._next
        
        node._next = self.__head
        temp._next = node
        self.__head = node
    
    def insert_at_end(self, data):
        node  = Node(data)

        if self.__head is None:
            self.__head = node
            node._next = self.__head
            return
        
        temp = self.__head
        while temp._next != self.__head:
            temp = temp._next
        
        temp._next = node
        node._next = self.__head

    def delete_from_end(self):
        if self.__head is None:
            return "Empty List!"
        
        if self.__head._next is self.__head:
            self.__head = None
            return

        temp = self.__head
        while temp._next._next != self.__head:
            temp = temp._next
        
        temp._next = self.__head

    def delete_from_beg(self):
        if self.__head is None:
            return "Empty List!"

        if self.__head._next is self.__head:
            self.__head = None
            return

        temp = self.__head
        while temp._next != self.__head:
            temp = temp._next

        self.__head = self.__head._next
        temp._next = self.__head

    def display(self):
        if self.__head is None:
            print("Empty List!")
            return
            
        temp = self.__head

        while True:
            print(temp._data, end="->")
            temp = temp._next
            if temp == self.__head:
                break
        
        print("(head)")
    

if __name__ == "__main__":
    cll = CLList()
    cll.insert_at_beg(10)
    cll.insert_at_beg(20)
    cll.insert_at_beg(30)
    cll.insert_at_beg(40)
    cll.insert_at_end(50)
    cll.insert_at_end(60)
    cll.delete_from_end()
    cll.delete_from_beg()
    cll.display()
