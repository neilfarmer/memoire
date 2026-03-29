"""DynamoDB client shared across all feature Lambdas."""

import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource("dynamodb")


def get_table(table_name: str):
    return dynamodb.Table(table_name)


def query_by_user(table, user_id: str) -> list[dict]:
    result = table.query(
        KeyConditionExpression=Key("user_id").eq(user_id)
    )
    return result.get("Items", [])


def get_item(table, user_id: str, sort_key_name: str, sort_key_value: str) -> dict | None:
    result = table.get_item(
        Key={"user_id": user_id, sort_key_name: sort_key_value}
    )
    return result.get("Item")


def delete_item(table, user_id: str, sort_key_name: str, sort_key_value: str) -> None:
    table.delete_item(
        Key={"user_id": user_id, sort_key_name: sort_key_value}
    )
