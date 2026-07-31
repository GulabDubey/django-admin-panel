import tensorflow as tf
import numpy as np

if __name__ == "__main__":
    x = np.array([1,2,3,4,5], dtype=float)
    y = np.array([2,4,6,8,10], dtype=float)

    model = tf.keras.Sequential([
        tf.keras.layers.Dense(units=1, input_shape=[1])
    ])

    model.compile(
        optimizer = 'sgd',
        loss = 'mean_squared_error'
    )

    model.fit(x, y, epochs=100)

    while True:
        user_input = input("Enter a number: ")

        if user_input in ["exit", "quit"]:
            break

        value = float(user_input)
        print(f"Your answer is: {model.predict(np.array([value]))}")