from pyspark.streaming import StreamingContext
from pyspark.streaming.kafka import KafkaUtils
from pyspark.sql import SparkSession
import json

spark = SparkSession.builder.appName("Python Spark Streaming").getOrCreate()

# загрузка схемы данных
tweet_example = spark.read.load("hdfs:///user/cloudera/schema_example.json", "json")

# название таблицы, куда мы будем сохранять
db_table = "default.tweets"

# путь к таблице
table_path = "hdfs:///user/cloudera/streamed-tweets-parquet"

# проверяем есть ли таблица: для каждой таблицы в spark.catalog.listTables() проверяем совпадает ли ее имя с нашей, если да, то возвращаем список совпавших
table_exists = [table for table in spark.catalog.listTables() if table.database+'.'+table.name == db_table]

# если список пустой - таблица не существует (создаем ее), если нет -существует
if not table_exists:
    
    # создаем пустой DataFrame
    df = spark.createDataFrame(sc.emptyRDD(), tweet_example.schema)
    
    # создаем таблицу
    df.write.saveAsTable(db_table, format='parquet', mode='overwrite', path='table_path')

# создаем контекст Spark Streaming c обновлением каждые 60 секунд
streamingContext = StreamingContext(spark.sparkContext, 60)

# подключаемся к Kafka, топик tweets, брокер quickstart.cloudera:9092
directKafkaStream = KafkaUtils.createDirectStream(streamingContext, ["tweets"], {"metadata.broker.list": "quickstart.cloudera:9092"})

# для накопившихся за 60 секунд данных (k, v) взять занчения (v) и перевести их в объект из json
tweets = directKafkaStream.map(lambda v: json.loads(v[1]))


def saveToTable(rdd):
    try:
        # Проверяем, что RDD не пустой
        if not rdd.isEmpty():
            # Создаем DataFrame. В качестве данных - RDD, в качестве схемы - схем примера
            df = spark.creatDataFrame(rdd, tweet_example.schema)
            # Дописываем в таблицу defualt.tweets
            df.write.mode("append").insertInto(db_table)
    except Exception as e:
        print("Ooops!", e)
    return rdd

tweets.foreachRDD(lambda x: saveToTable(x))

# запустить Streaming
streamingContext.start()

# ждать прерывания
streamingContext.awaitTermination()