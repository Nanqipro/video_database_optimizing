import cv2
import torch
import csv
import mysql.connector
from mysql.connector import Error

# 使用YOLOv5目标检测算法对视频逐帧目标检测和并提取关键帧中的对象
# 此算法基于pytorch框架，对于检测结果构建索引并存入csv文件中和MySQL数据库中
# 优化方法：1、目标检测算法运用GPU进行加速计算，大大降低了训练耗时，提高了运算效率
#         2、使用批处理和预编译语句优化数据库操作


# 加载预训练的YOLOv5模型
model = torch.hub.load('ultralytics/yolov5', 'yolov5s', pretrained=True)


# 检查GPU是否可用并加载模型到GPU
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
# model = torch.hub.load('ultralytics/yolov5', 'yolov5s', pretrained=True).to(device)


# 定义处理视频的函数
def process_video(video_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Error: Could not open video.")
        return

    frame_index = 0
    detections = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = model(frame_rgb)
        results_data = results.pandas().xyxy[0]
        detections.append({
            'frame_index': frame_index,
            'detections': results_data.to_dict(orient='records')
        })
        frame_index += 1

    cap.release()
    return detections


# 构建索引（创建一个字典来存储每个对象标签及其出现的帧和时间码）
def build_index(detections, fps):
    index = {}
    for detection in detections:
        frame_index = detection['frame_index']
        time_stamp = frame_index / fps  # 计算时间戳
        for det in detection['detections']:
            label = det['name']
            if label not in index:
                index[label] = []
            index[label].append({'frame_index': frame_index, 'time_stamp': time_stamp, 'confidence': det['confidence']})
    return index

# 将结果保存入csv文件中
def save_index_to_csv(index, csv_file_path):
    with open(csv_file_path, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Label', 'Frame Index', 'Time Stamp', 'Confidence'])

        for label, entries in index.items():
            for entry in entries:
                writer.writerow(
                    [label, entry['frame_index'], f"{entry['time_stamp']:.2f}", f"{entry['confidence']:.2f}"])

# 连接到MySql数据库
def connect_to_mysql():
    try:
        connection = mysql.connector.connect(
            host='localhost',
            user='root',
            password='8729512929abc',
            database='video_analysis'
        )
        if connection.is_connected():
            db_Info = connection.get_server_info()
            print("Connected to MySql Server version ", db_Info)
            return connection
    except Error as e:
        print("Error while connecting to MySql", e)

# 插入检测数据到数据库
# def insert_objects(index):
#     connection = connect_to_mysql()
#     if connection is not None:
#         cursor = connection.cursor()
#         insert_query = """
#         INSERT INTO objects (label, frame_index, time_stamp, confidence)
#         VALUES (%s, %s, %s, %s)
#         """
#         for label, entries in index.items():
#             for entry in entries:
#                 data_tuple = (label, entry['frame_index'], entry['time_stamp'], entry['confidence'])
#                 cursor.execute(insert_query, data_tuple)
#         connection.commit()
#         print("Data inserted successfully")
#         cursor.close()
#         connection.close()

# 改进后使用批处理和预编译语句优化数据库操作
# （逐条执行插入操作效率低下，尤其是在处理大量数据时。所以通过使用预编译语句和批处理来优化这一过程。）
def insert_objects(index):
    connection = connect_to_mysql()
    if connection is not None:
        cursor = connection.cursor(prepared=True)
        insert_query = """
        INSERT INTO objects (label, frame_index, time_stamp, confidence)
        VALUES (%s, %s, %s, %s)
        """
        batch_data = []
        for label, entries in index.items():
            for entry in entries:
                data_tuple = (label, entry['frame_index'], entry['time_stamp'], entry['confidence'])
                batch_data.append(data_tuple)
                if len(batch_data) >= 1000:  # 批量插入，每批1000条
                    cursor.executemany(insert_query, batch_data)
                    batch_data = []
        if batch_data:  # 插入剩余的数据
            cursor.executemany(insert_query, batch_data)
        connection.commit()
        print("Data inserted successfully")
        cursor.close()
        connection.close()

video_path = 'video/animals.mp4'
video_detections = process_video(video_path)

video = cv2.VideoCapture('video/animals.mp4')
# 获取视频的帧率
fps = video.get(cv2.CAP_PROP_FPS)
print("Frame rate:", fps)

# 使用前面的检测结果构建索引
index = build_index(video_detections, fps)

# 打印构建的索引以查看结果
for label, entries in index.items():
    print(f"Label: {label}")
    for entry in entries:
        print(f"  Frame: {entry['frame_index']}, Time: {entry['time_stamp']:.2f}s, Confidence: {entry['confidence']:.2f}")

csv_file_path = 'video_index.csv'
save_index_to_csv(index, csv_file_path)
print("Index has been saved to CSV file successfully.")
insert_objects(index)
print("Index has been saved to MySql successfully.")

