#STARK Code Generator component.
#Produces the customized static content for a STARK system

#Python Standard Library
import base64
import textwrap

#Private modules
import cgstatic_relationships as cg_rel
import convert_friendly_to_system as converter

def create(data):

    project = data["Project Name"]
    entity  = data["Entity"]
    cols    = data["Columns"]

    #Convert human-friendly names to variable-friendly names
    entity_varname = converter.convert_to_system_name(entity)

    source_code = f"""\
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
            <meta http-equiv="content-type" content="text/html; charset=UTF-8" />

            <link rel="stylesheet" href="css/bootstrap.min.css" />
            <link rel="stylesheet" href="css/bootstrap-vue.css" />
            <link rel="stylesheet" href="css/STARK.css" />

            <script src="js/vue.js" defer></script>
            <script src="js/bootstrap-vue.min.js" defer></script>
            <script src="js/STARK.js" defer></script>
            <script src="js/STARK_spinner.js" defer></script>
            <script src="js/STARK_loading_modal.js" defer></script>
            <script src="js/{entity_varname}_app.js" defer></script>
            <script src="js/{entity_varname}_view.js" defer></script>"""

    #Figure out which other _app.js files we need to add based on relationships
    for col, col_type in cols.items():
        entities = cg_rel.get({
            "col": col,
            "col_type": col_type,
        })
    
        for related in entities:
            related_varname = converter.convert_to_system_name(related)
            source_code += f"""
            <script src="js/{related_varname}_app.js" defer></script>"""

    source_code += f"""
            <script src="js/generic_root_get.js" defer></script>

            <title>{project} - {entity}</title>
        </head>
"""


    return source_code