class SortingAlgo:
    @staticmethod
    def bubbleSort(arr):
        n = len(arr)
        for i in range(n):
            for j in range(n-1-i):
                if arr[j] > arr[j+1]:
                    [arr[j], arr[j+1]]= [arr[j+1], arr[j]]
        return arr
        
    # selection sort: find the minimum element and then swap with the minimum element
    @staticmethod
    def selectionSort(arr): 
        n = len(arr)

        for i in range(n):
            min_index = i
            for j in range(i+1, n):
                if  arr[j] < arr[min_index]:
                    min_index = j 

            arr[i], arr[min_index] = arr[min_index], arr[i]

        return arr

    @staticmethod
    def insertionSort(arr):
        return arr
    
    @staticmethod
    def quickSort(arr):
        if len(arr) == 1:
            return
        
        mid = len(arr)/2
        left = SortingAlgo.quickSort(arr[:min])
        right = SortingAlgo.quickSort(arr[min:])

        return left + right

    @staticmethod
    def mergeSort(arr):
        return arr
    

if __name__ == "__main__":
    print(SortingAlgo.bubbleSort([12,13,11,15,14]))
    print(SortingAlgo.selectionSort([12,13,11,15,14]))