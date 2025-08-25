import os
from pymongo import MongoClient
from redis import Redis
from rq import Worker, Queue, Connection

listen = ['default']

# 从环境变量获取配置，提供默认值以方便本地测试
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
mongo_url = os.getenv('MONGO_URL', 'mongodb://localhost:27017/')

# --- 数据库连接 ---
# 在worker启动时建立一次连接，而不是在每个任务中都重新连接
client = MongoClient(mongo_url)
db = client.feishu_card_interactions

# --- 任务处理函数 ---

def save_interaction_to_db(interaction_data):
    """将单条交互数据存入MongoDB."""
    try:
        # 1. 从交互数据中获取 message_id
        message_id = interaction_data.get('event', {}).get('message', {}).get('message_id')
        if not message_id:
            print("错误：交互数据中未找到 message_id")
            return False

        # 2. 使用 message_id 查询 card_context 集合，获取卡片上下文（如标题）
        card_context = db.card_context.find_one({"message_id": message_id})
        card_title = card_context.get('card_title', '未知标题') if card_context else '未知标题'

        # 3. 准备要存入数据库的完整文档
        record = {
            "message_id": message_id,
            "card_title": card_title,
            "user_id": interaction_data.get('event', {}).get('operator', {}).get('open_id'),
            "interaction_time": interaction_data.get('event', {}).get('action', {}).get('action_time'),
            "interaction_tag": interaction_data.get('event', {}).get('action', {}).get('tag'),
            "value": interaction_data.get('event', {}).get('action', {}).get('value'),
            "raw_data": interaction_data # 同时保存原始回调数据，便于未来追溯
        }

        # 4. 插入到 interactions 集合
        db.interactions.insert_one(record)
        print(f"成功处理并存储了 message_id: {message_id} 的交互")
        return True
    except Exception as e:
        print(f"处理交互数据时出错: {e}")
        return False

if __name__ == '__main__':
    # 监听默认队列
    redis_conn = Redis.from_url(redis_url)
    q = Queue(connection=redis_conn)

    with Connection(redis_conn):
        # 启动worker，处理队列中的任务
        # 每个任务都会调用 save_interaction_to_db 函数
        worker = Worker(queues=[q], connection=redis_conn)
        worker.work()