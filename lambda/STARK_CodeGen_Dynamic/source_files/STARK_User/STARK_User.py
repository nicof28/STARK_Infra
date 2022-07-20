#Python Standard Library
import base64
import json
import sys
from urllib.parse import unquote

#Extra modules
import boto3
import stark_scrypt as scrypt

ddb = boto3.client('dynamodb')

#######
#CONFIG
ddb_table   = "[[STARK_DDB_TABLE_NAME]]"
pk_field    = "Username"
default_sk  = "STARK|user|info"
sort_fields = ["Username", ]
page_limit  = 10

def lambda_handler(event, context):

    #Get request type
    request_type = event.get('queryStringParameters',{}).get('rt','')

    if request_type == '':
        ########################
        #Handle non-GET requests

        #Get specific request method
        method  = event.get('requestContext').get('http').get('method')

        if event.get('isBase64Encoded') == True :
            payload = json.loads(base64.b64decode(event.get('body'))).get('STARK_User',"")
        else:    
            payload = json.loads(event.get('body')).get('STARK_User',"")

        data    = {}

        if payload == "":
            return {
                "isBase64Encoded": False,
                "statusCode": 400,
                "body": json.dumps("Client payload missing"),
                "headers": {
                    "Content-Type": "application/json",
                }
            }
        else:
            data['pk'] = payload.get('Username')
            data['orig_pk'] = payload.get('orig_Username','')
            data['sk'] = payload.get('sk', '')
            if data['sk'] == "":
                data['sk'] = default_sk
            data['Full_Name'] = payload.get('Full_Name','')
            data['Nickname'] = payload.get('Nickname','')
            data['Password_Hash'] = payload.get('Password_Hash','')
            data['Role'] = payload.get('Role','')
        ListView_index_values = []
        for field in sort_fields:
            ListView_index_values.append(payload.get(field))
        data['STARK-ListView-sk'] = "|".join(ListView_index_values)

        if method == "DELETE":
            response = delete(data)

        elif method == "PUT":

            #We can't update DDB PK, so if PK is different, we need to do ADD + DELETE
            if data['orig_pk'] == data['pk']:
                response = edit(data)
            else:
                response   = add(data)
                data['pk'] = data['orig_pk']
                response   = delete(data)

        elif method == "POST":
            response = add(data)

        else:
            return {
                "isBase64Encoded": False,
                "statusCode": 400,
                "body": json.dumps("Could not handle API request"),
                "headers": {
                    "Content-Type": "application/json",
                }
            }

    else:
        ####################
        #Handle GET requests
        if request_type == "all":
            #check for submitted token
            lv_token = event.get('queryStringParameters',{}).get('nt', None)
            if lv_token != None:
                lv_token = unquote(lv_token)
                lv_token = json.loads(lv_token)

            items, next_token = get_all(default_sk, lv_token)

            response = {
                'Next_Token': json.dumps(next_token),
                'Items': items
            }

        elif request_type == "report":
            response = report(default_sk)

        elif request_type == "detail":

            pk = event.get('queryStringParameters').get('Username','')
            sk = event.get('queryStringParameters').get('sk','')
            if sk == "":
                sk = default_sk

            response = get_by_pk(pk, sk)
        else:
            return {
                "isBase64Encoded": False,
                "statusCode": 400,
                "body": json.dumps("Could not handle GET request - unknown request type"),
                "headers": {
                    "Content-Type": "application/json",
                }
            }

    return {
        "isBase64Encoded": False,
        "statusCode": 200,
        "body": json.dumps(response),
        "headers": {
            "Content-Type": "application/json",
        }
    }

def report(sk=default_sk):
    #FIXME: THIS IS A STUB, WILL NEED TO BE UPDATED WITH
    #   ENHANCED LISTVIEW LOGIC LATER WHEN WE ACTUALLY IMPLEMENT REPORTING

    response = ddb.query(
        TableName=ddb_table,
        IndexName="STARK-ListView-Index",
        Select='ALL_ATTRIBUTES',
        ReturnConsumedCapacity='TOTAL',
        KeyConditionExpression='sk = :sk',
        ExpressionAttributeValues={
            ':sk' : {'S' : sk}
        }
    )

    raw = response.get('Items')

    #Map to expected structure
    #FIXME: this is duplicated code, make this DRY by outsourcing the mapping to a different function.
    items = []
    for record in raw:
        item = {}
        item['Username'] = record.get('pk', {}).get('S','')
        item['sk'] = record.get('sk',{}).get('S','')
        item['Full_Name'] = record.get('Full_Name',{}).get('S','')
        item['Nickname'] = record.get('Nickname',{}).get('S','')
        item['Password_Hash'] = record.get('Password_Hash',{}).get('S','')
        item['Role'] = record.get('Role',{}).get('S','')
        items.append(item)

    return items

def get_all(sk=default_sk, lv_token=None):

    if lv_token == None:
        response = ddb.query(
            TableName=ddb_table,
            IndexName="STARK-ListView-Index",
            Select='ALL_ATTRIBUTES',
            Limit=page_limit,
            ReturnConsumedCapacity='TOTAL',
            KeyConditionExpression='sk = :sk',
            ExpressionAttributeValues={
                ':sk' : {'S' : sk}
            }
        )
    else:
        response = ddb.query(
            TableName=ddb_table,
            IndexName="STARK-ListView-Index",
            Select='ALL_ATTRIBUTES',
            Limit=page_limit,
            ExclusiveStartKey=lv_token,
            ReturnConsumedCapacity='TOTAL',
            KeyConditionExpression='sk = :sk',
            ExpressionAttributeValues={
                ':sk' : {'S' : sk}
            }
        )

    raw = response.get('Items')

    #Map to expected structure
    #FIXME: this is duplicated code, make this DRY by outsourcing the mapping to a different function.
    items = []
    for record in raw:
        item = {}
        item['Username'] = record.get('pk', {}).get('S','')
        item['sk'] = record.get('sk',{}).get('S','')
        item['Full_Name'] = record.get('Full_Name',{}).get('S','')
        item['Nickname'] = record.get('Nickname',{}).get('S','')
        item['Role'] = record.get('Role',{}).get('S','')

        items.append(item)
    #NOTE: We explicitly left out the password hash. Since this is the generic "get all records" function, there's really no
    #   legitimate reason to get something as sensitive as the passwordh hash. Functionality that actually has to mass list
    #   users alongside their password hashes will have to use a function specifically made for that. Safety first.

    #Get the "next" token, pass to calling function. This enables a "next page" request later.
    next_token = response.get('LastEvaluatedKey')

    return items, next_token

def get_by_pk(pk, sk=default_sk):
    response = ddb.query(
        TableName=ddb_table,
        Select='ALL_ATTRIBUTES',
        KeyConditionExpression="#pk = :pk and #sk = :sk",
        ExpressionAttributeNames={
            '#pk' : 'pk',
            '#sk' : 'sk'
        },
        ExpressionAttributeValues={
            ':pk' : {'S' : pk },
            ':sk' : {'S' : sk }
        }
    )

    raw = response.get('Items')

    #FIXME: Mapping is duplicated code, make this DRY
    #Map to expected structure
    items = []
    for record in raw:
        item = {}
        item['Username'] = record.get('pk', {}).get('S','')
        item['sk'] = record.get('sk',{}).get('S','')
        item['Full_Name'] = record.get('Full_Name',{}).get('S','')
        item['Nickname'] = record.get('Nickname',{}).get('S','')
        item['Role'] = record.get('Role',{}).get('S','')
        items.append(item)
    #NOTE: We explicitly left out the password hash. Functionality that requires the user record along with the password hash should use 
    #       a specialized function instead of the generic "get" function.

    return items

def delete(data):
    pk = data.get('pk','')
    sk = data.get('sk','')
    if sk == '': sk = default_sk

    response = ddb.delete_item(
        TableName=ddb_table,
        Key={
            'pk' : {'S' : pk},
            'sk' : {'S' : sk}
        }
    )

    return "OK"

def edit(data):                
    pk = data.get('pk', '')
    sk = data.get('sk', '')
    if sk == '': sk = default_sk
    Full_Name = str(data.get('Full_Name', ''))
    Nickname = str(data.get('Nickname', ''))
    Password_Hash = str(data.get('Password_Hash', ''))
    Role = str(data.get('Role', ''))

    UpdateExpressionString = "SET #Full_Name = :Full_Name, #Nickname = :Nickname, #Role = :Role" 
    ExpressionAttributeNamesDict = {
        '#Full_Name' : 'Full_Name',
        '#Nickname' : 'Nickname',
        '#Role' : 'Role',
    }
    ExpressionAttributeValuesDict = {
        ':Full_Name' : {'S' : Full_Name },
        ':Nickname' : {'S' : Nickname },
        ':Role' : {'S' : Role },
    }

    #If Password_Hash is not an empty string, this means it's a password reset request.
    if Password_Hash != '':
        UpdateExpressionString += ", #Password_Hash = :Password_Hash"
        ExpressionAttributeNamesDict['#Password_Hash'] = 'Password_Hash'
        ExpressionAttributeValuesDict[':Password_Hash'] = {'S': scrypt.create_hash(Password_Hash)}

    STARK_ListView_sk = data.get('STARK-ListView-sk','')
    if STARK_ListView_sk == '':
        STARK_ListView_sk = create_listview_index_value(data)

    UpdateExpressionString += ", #STARKListViewsk = :STARKListViewsk"
    ExpressionAttributeNamesDict['#STARKListViewsk']  = 'STARK-ListView-sk'
    ExpressionAttributeValuesDict[':STARKListViewsk'] = {'S' : data['STARK-ListView-sk']}

    response = ddb.update_item(
        TableName=ddb_table,
        Key={
            'pk' : {'S' : pk},
            'sk' : {'S' : sk}
        },
        UpdateExpression=UpdateExpressionString,
        ExpressionAttributeNames=ExpressionAttributeNamesDict,
        ExpressionAttributeValues=ExpressionAttributeValuesDict
    )

    assign_role_permissions({'Username': pk, 'Role': Role })

    return "OK"

def add(data):
    pk = data.get('pk', '')
    sk = data.get('sk', '')
    if sk == '': sk = default_sk
    Full_Name = str(data.get('Full_Name', ''))
    Nickname = str(data.get('Nickname', ''))
    Password_Hash = str(data.get('Password_Hash', ''))
    Role = str(data.get('Role', ''))

    item={}
    item['pk'] = {'S' : pk}
    item['sk'] = {'S' : sk}
    item['Full_Name'] = {'S' : Full_Name}
    item['Nickname'] = {'S' : Nickname}
    item['Password_Hash'] = {'S' : scrypt.create_hash(Password_Hash)}
    item['Role'] = {'S' : Role}

    if data.get('STARK-ListView-sk','') == '':
        item['STARK-ListView-sk'] = {'S' : create_listview_index_value(data)}
    else:
        item['STARK-ListView-sk'] = {'S' : data['STARK-ListView-sk']}
    response = ddb.put_item(
        TableName=ddb_table,
        Item=item,
    )

    assign_role_permissions({'Username': pk, 'Role': Role })

    return "OK"

def compose_operators(key, data):
    composed_filter_dict = {"filter_string":"","expression_values": {}}
    if data['operator'] == "IN":
        string_split = data['value'].split(',')
        composed_filter_dict['filter_string'] += f" {key} IN "
        temp_in_string = ""
        in_string = ""
        in_counter = 1
        for in_index in string_split:
            in_string += f" :inParam{in_counter}, "
            composed_filter_dict['expression_values'][f":inParam{in_counter}"] = {data['type'] : in_index.strip()}
            in_counter += 1
        temp_in_string = in_string[1:-2]
        composed_filter_dict['filter_string'] += f"({temp_in_string}) AND"
    elif data['operator'] in [ "contains", "begins_with" ]:
        composed_filter_dict['filter_string'] += f" {data['operator']}({key}, :{key}) AND"
        composed_filter_dict['expression_values'][f":{key}"] = {data['type'] : data['value'].strip()}
    elif data['operator'] == "between":
        from_to_split = data['value'].split(',')
        composed_filter_dict['filter_string'] += f" ({key} BETWEEN :from{key} AND :to{key}) AND"
        composed_filter_dict['expression_values'][f":from{key}"] = {data['type'] : from_to_split[0].strip()}
        composed_filter_dict['expression_values'][f":to{key}"] = {data['type'] : from_to_split[1].strip()}
    else:
        composed_filter_dict['filter_string'] += f" {key} {data['operator']} :{key} AND"
        composed_filter_dict['expression_values'][f":{key}"] = {data['type'] : data['value'].strip()}

    return composed_filter_dict

def create_listview_index_value(data):
    ListView_index_values = []
    for field in sort_fields:
        if field == pk_field:
            ListView_index_values.append(data['pk'])
        else:
            ListView_index_values.append(data.get(field))
    STARK_ListView_sk = "|".join(ListView_index_values)
    return STARK_ListView_sk

def assign_role_permissions(data):
    username  = data['Username']
    role_name = data['Role']
 
    from os import getcwd 
    STARK_folder = getcwd() + '/STARK_User_Roles'
    sys.path = [STARK_folder] + sys.path
    import STARK_User_Roles as user_roles

    response = user_roles.get_by_pk(role_name)
    permissions = response[0]['Permissions']
    
    sys.path[0] = getcwd() + '/STARK_User_Permissions'
    import STARK_User_Permissions as user_permissions
    data = {
        'pk': username,
        'Permissions': permissions
    }
    response = user_permissions.add(data)

    return "OK"

def get_all_by_old_parent_value(old_pk_val, sk = default_sk):
    
    string_filter = " #Role = :old_parent_value"
    object_expression_value = {':sk' : {'S' : sk},
                                ':old_parent_value': {'S' : old_pk_val}}
    ExpressionAttributeNamesDict = {
        '#Role' : 'Role',
    }
    response = ddb.query(
        TableName=ddb_table,
        IndexName="STARK-ListView-Index",
        Select='ALL_ATTRIBUTES',
        ReturnConsumedCapacity='TOTAL',
        FilterExpression=string_filter,
        KeyConditionExpression='sk = :sk',
        ExpressionAttributeValues=object_expression_value,
        ExpressionAttributeNames=ExpressionAttributeNamesDict
    )
    raw = response.get('Items')
    items = []
    for record in raw:
        item = {}
        item['pk'] = record.get('pk', {}).get('S','')
        item['sk'] = record.get('sk',{}).get('S','')
        item['Full_Name'] = record.get('Full_Name',{}).get('S','')
        item['Nickname'] = record.get('Nickname',{}).get('S','')
        item['Role'] = record.get('Role',{}).get('S','')
        item['STARK-ListView-sk'] = record.get('STARK-ListView-sk',{}).get('S','')
        items.append(item)

    return items