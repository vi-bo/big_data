from io import BytesIO
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

def get_as_base64(img_content):
    # кодируем данные при помощи только 64 символов ASCII
    return base64.b64encode(img_content)

def getFacesCount(img_content):
    # определяем сколько лиц на фотографии
    image = face_recognition.load_image_file(BytesIO(img_content))
    return len(face_recognition.face_locations(image))

# vibo: подготовка документа, на вход функция получает твит
def get_solr_doc(tweet):
    # формируем url фотографии профиля
    user_url = 'https://twitter.com/{screen_name}/profile_image?size=original'.format(
        screen_name=tweet['user']['screen_name'])
    # выкачиваем фотографию
    img_content = requests.get(user_url).content
    # определяем количество лиц на фотографии (функция getFacesCount)
    faces = getFacesCount(img_content)
    if faces > 0:
        # готовим документы
        return {'id': tweet['id'], \
                        'user_screen_name': tweet['user']['screen_name'], \
                        'user_name': tweet['user']['name'], \
                        'user_url': user_url, \
                        'user_base64_img': get_as_base64(img_content), \
                        'faces_count': faces, \
                        'text': tweet['text'], \
                        'user_lang': tweet['user']['lang'], \
                        'user_friends_count': tweet['user']['friends_count']}
    else:
        return None

def insert_into_solr(for_solr_docs):
    # подключаемся к Zookeeper
    zookeeper = pysolr.ZooKeeper("quickstart.cloudera:2181/solr")
    # получаем коллекцию
    solr = pysolr.SolrCloud(zookeeper, "tweets")
    # индексируем документы
    solr.add(for_solr_docs)
    return for_solr_docs

def indexToSolr(rdd):
    try:
        # vibo: если rdd не пустой
        if not rdd.isEmpty():
            # vibo: вызываем функцию, которая для каждой записи в rdd (для каждого твита) вызывает get_solr_doc()
            # vibo: готовим документ для Solr
            docs = rdd.map(lambda tweet: get_solr_doc(tweet))
            # vibo: фильтруем, чтобы оставить все не пустые документы
            for_solr = docs.filter(lambda doc: doc != None)
            # vibo: если такие документы остались
            if not for_solr.isEmpty():
                # vibo: вызываем функцию mapPartitions, которая для каждой партиции выполняет вставку в Solr
                # vibo: для каждой партиции, чтобы создавать одно подключение с каждого узла, чтобы не создавать новое подключение для каждой записи
                # vibo: count() чтобы заставить Spark работать
                for_solr.mapPartitions(lambda partition: insert_into_solr(partition)).count()
    except Exception as e:
        print("Ooops solr!", e)
    return rdd

tweets.foreachRDD(lambda x: saveToTable(x))
# vibo: добавляем функцию, которая будет индексировать в Solr
tweets.foreachRDD(lambda x: indexToSolr(x))
# запустить Streaming
streamingContext.start()
# ждать прерывания
streamingContext.awaitTermination()