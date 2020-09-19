#STARK Code Generator component.
#Produces the customized dynamic content for a STARK system

#Python Standard Library
import base64
import textwrap

def create(data):
  
    pk             = data["PK"]
    entity         = data["Entity"]
    model          = data["Columns"]
    ddb_table_name = data["DynamoDB Name"]

    #Convert human-friendly names to variable-friendly names
    entity_varname = entity.replace(" ", "_").lower()
    pk_varname     = entity.replace(" ", "_").lower()

    default_sk     = entity + "|info"

    #FIXME "model" here is actually just the columns, not the entire model; 
    #   we're stuck with older variable naming that pre-dates our current structure
    #   Fix when able
 
    #Create the column list value we'll use in the code as a declaration
    col_list = "pk, sk, "
    for col in model:
        col_varname = col.replace(" ", "_").lower()
        col_list += col_varname + ", "
    col_list = col_list[:-2]
    #FIXME - this is unwieldy for tables with a ton of columns. Make this a dictionary of {column_name: column_value}

    #This is for our DDB update call
    update_expression = ""
    for col in model:
        col_varname = col.replace(" ", "_").lower()
        update_expression += f"""#{col_varname} = :{col_varname}, """
    update_expression = update_expression[:-2]

    source_code = f"""\
    #Python Standard Library
    import base64
    import json

    #Extra modules
    import boto3

    ddb = boto3.client('dynamodb')

    #######
    #CONFIG
    ddb_table  = "{ddb_table_name}"
    default_sk = "{default_sk}"

    def lambda_handler(event, context):

        #Get request type
        request_type = event.get('queryStringParameters',{{}}).get('rt','')

        if request_type == '':
            ########################
            #Handle non-GET requests
    
            #Get specific request method
            method  = event.get('requestContext').get('http').get('method')
            payload = json.loads(event.get('body')).get('{entity_varname}',"")

            if payload == "":
                return {{
                    "isBase64Encoded": False,
                    "statusCode": 400,
                    "body": json.dumps("Client payload missing"),
                    "headers": {{
                        "Content-Type": "application/json",
                    }}
                }}
            else:
                pk = payload.get('{pk_varname}')
                orig_pk = payload.get('orig_{pk_varname}','')
                sk = payload.get('sk', '')
                if sk == "":
                    sk = default_sk"""

    for col, col_type in model.items():
        col_varname = col.replace(" ", "_").lower()
        source_code +=f"""
                {col_varname} = payload.get('{col_varname}','')"""

    source_code +=f"""

            if method == "DELETE":
                response = delete(pk, sk)

            elif method == "PUT":

                #We can't update DDB PK, so if PK is different, we need to do ADD + DELETE
                if orig_pk == pk:
                    response = edit({col_list})
                else:
                    response = add({col_list})
                    response = delete(orig_pk, sk)

            elif method == "POST":
                response = add({col_list})

            else:
                return {{
                    "isBase64Encoded": False,
                    "statusCode": 400,
                    "body": json.dumps("Could not handle API request"),
                    "headers": {{
                        "Content-Type": "application/json",
                    }}
                }}

        else:
            ####################
            #Handle GET requests
            if request_type == "all":
                response = get_all(default_sk)

            elif request_type == "detail":

                pk = event.get('queryStringParameters').get('{pk_varname}','')
                sk = event.get('queryStringParameters').get('sk','')
                if sk == "":
                    sk = default_sk

                response = get_by_pk(pk, sk)
            else:
                return {{
                    "isBase64Encoded": False,
                    "statusCode": 400,
                    "body": json.dumps("Could not handle GET request - unknown request type"),
                    "headers": {{
                        "Content-Type": "application/json",
                    }}
                }}

        return {{
            "isBase64Encoded": False,
            "statusCode": 200,
            "body": json.dumps(response),
            "headers": {{
                "Content-Type": "application/json",
            }}
        }}

    def get_all(sk):
        response = ddb.scan(
            TableName=ddb_table,
            Select='ALL_ATTRIBUTES',
            ReturnConsumedCapacity='TOTAL',
            FilterExpression='#sk = :sk',
            ExpressionAttributeNames={{
                '#sk' : 'sk'
            }},
            ExpressionAttributeValues={{
                ':sk' : {{'S' : sk}}
            }}
        )

        raw = response.get('Items')

        #Map to expected structure
        #FIXME: this is duplicated code, make this DRY by outsourcing the mapping to a different function.
        items = []
        for record in raw:
            item = {{'{pk_varname}': record['pk']['S'],
                    'sk': record['sk']['S'],"""

    for col, col_type in model.items():
        #FIXME: [Dupe 0] This transformation is a stub, and it should be done earlier. Only final processed data should be here
        #   The parser should have done the work for us. It's possible that both the original and transformed types need to be
        #   retained, for different purposes. The original type has metadata value that may affect other codegen decisions, aside
        #   from having a counterpart for DDB datatypes
        col_varname = col.replace(" ", "_").lower()
        if col_type == 'string':
            col_type = 'S'
        elif col_type == "int":
            col_type = 'N'
        else:
            col_type = 'S'

        source_code +=f"""
                    '{col_varname}': record['{col_varname}']['{col_type}'],"""


    source_code +=f"""}}
            items.append(item)

        #Sort: this can be transformed to an actual sorting function instead of lambda (Python lambda, not AWS lambda)
        #   to allow for sorting features like choosing which column to sort on, or applying complex sort logic that involves two or more cols.
        items = sorted(items, key=lambda item: item['{pk_varname}'])

        return items

    def get_by_pk(pk, sk):
        response = ddb.query(
            TableName=ddb_table,
            Select='ALL_ATTRIBUTES',
            KeyConditionExpression="#pk = :pk and #sk = :sk",
            ExpressionAttributeNames={{
                '#pk' : 'pk',
                '#sk' : 'sk'
            }},
            ExpressionAttributeValues={{
                ':pk' : {{'S' : pk }},
                ':sk' : {{'S' : sk }}
            }}
        )

        raw = response.get('Items')

        #Map to expected structure
        items = []
        for record in raw:
            item = {{'{pk_varname}': record['pk']['S'],
                    'sk': record['sk']['S'],"""

    for col, col_type in model.items():
        #FIXME: [Dupe 0] This transformation is a stub, and it should be done earlier. Only final processed data should be here
        #   The parser should have done the work for us. It's possible that both the original and transformed types need to be
        #   retained, for different purposes. The original type has metadata value that may affect other codegen decisions, aside
        #   from having a counterpart for DDB datatypes
        col_varname = col.replace(" ", "_").lower()
        if col_type == 'string':
            col_type = 'S'
        elif col_type == "int":
            col_type = 'N'
        else:
            col_type = 'S'

        source_code +=f"""
                    '{col_varname}': record['{col_varname}']['{col_type}'],"""


    source_code += f"""}}
            items.append(item)
        #FIXME: Mapping is duplicated code, make this DRY

        return items

    def delete(pk, sk):
        response = ddb.delete_item(
            TableName=ddb_table,
            Key={{
                'pk' : {{'S' : pk}},
                'sk' : {{'S' : sk}}
            }}
        )

        return "OK"

    def edit({col_list}):                

        response = ddb.update_item(
            TableName=ddb_table,
            Key={{
                'pk' : {{'S' : pk}},
                'sk' : {{'S' : sk}}
            }},
            UpdateExpression="SET {update_expression}",
            ExpressionAttributeNames={{"""

    for col in model:
        col_varname = col.replace(" ", "_").lower()
        source_code +=f"""
                '#{col_varname}' : '{col_varname}',"""  

    source_code += f"""
            }},
            ExpressionAttributeValues={{"""

    for col, col_type in model.items():
        #FIXME: [Dupe 2] This transformation is a stub, and it should be done earlier. Only final processed data should be here
        #   The parser should have done the work for us. It's possible that both the original and transformed types need to be
        #   retained, for different purposes. The original type has metadata value that may affect other codegen decisions, aside
        #   from having a counterpart for DDB datatypes
        col_varname = col.replace(" ", "_").lower()
        if col_type == 'string':
            col_type = 'S'
        elif col_type == "int":
            col_type = 'N'
        else:
            col_type = 'S'

        source_code +=f"""
                ':{col_varname}' : {{'{col_type}' : {col_varname} }},"""  

    source_code += f"""
            }}
        )

        return "OK"

    def add({col_list}):

        item={{}}
        item['pk'] = {{'S' : pk}}
        item['sk'] = {{'S' : sk}}"""

    for col, col_type in model.items():
        #FIXME: [Dupe 3] This transformation is a stub, and it should be done earlier. Only final processed data should be here
        #   The parser should have done the work for us. It's possible that both the original and transformed types need to be
        #   retained, for different purposes. The original type has metadata value that may affect other codegen decisions, aside
        #   from having a counterpart for DDB datatypes
        col_varname = col.replace(" ", "_").lower()
        if col_type == 'string':
            col_type = 'S'
        elif col_type == "int":
            col_type = 'N'
        else:
            col_type = 'S'

        source_code +=f"""
        item['{col_varname}'] = {{'{col_type}' : {col_varname}}}"""

    source_code += f"""
        response = ddb.put_item(
            TableName=ddb_table,
            Item=item,
        )

        return "OK"
    """

    return textwrap.dedent(source_code)