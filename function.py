from transmissionV2 import transmit_folder

results = transmit_folder(
    folder=r"/home/ras1/Desktop/2026Project/transmission/Images",
    baud=115200,
    verbose=False
)
print(results)
