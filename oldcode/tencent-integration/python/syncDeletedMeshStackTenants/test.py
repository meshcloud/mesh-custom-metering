import json, base64, logging, os, traceback
from typing import Dict

#import env_manager
import mesh_client
import mail_client

from jinja2 import Environment, FileSystemLoader

import functions_framework
import google.cloud.logging
from google.cloud import secretmanager
from cloudevents.http import CloudEvent

# Lookup if each meshStack tenant still exists in Tencent
# if the tenant does not exist, save as tenant to be deleted
def findDeletedTenants(inventory):   
    listTenantsToDelete = []
    try:
        meshStackInventory = inventory["meshStack"]
        tencentInventory = inventory["tencent"]
        for tenant in meshStackInventory:
            if not (tenant in tencentInventory):  # meshStack tenant does not exist in Tencent, i.e. was deleted at source
                listTenantsToDelete.append(
                    {
                        "localId": tenant,
                        "tenantIdentifier": meshStackInventory[tenant]["tenantIdentifier"],
                    }
                )
    except Exception as e:
        logging.error(f"Error while extracting deleted tenants: {str(e)} {traceback.format_exc()}")
        listTenantsToDelete = []
        
    return listTenantsToDelete

# Lookup if each Tencent account already exists in meshStack
# if the account does not exist, save as tenant to be imported
def findNewdTenants(inventory):
    listTenantsToCreate = []
    try:
        meshStackInventory = inventory["meshStack"]
        tencentInventory = inventory["tencent"]
        for account in tencentInventory:
            if not (
                account in meshStackInventory
            ):  # meshStack tenant does not exist in Tencent, i.e. was deleted at source
                listTenantsToCreate.append(
                    {
                        "localId": account,
                        "projectDisplayName": tencentInventory[account]["Name"],
                        "landingZoneId": tencentInventory[account]["NodeId"],
                    }
                )
    except Exception as e:
        logging.error(f"Error while extracting new tenants: {str(e)} {traceback.format_exc()}")
        listTenantsToCreate = []
    return listTenantsToCreate

def render_email_template(template_name, context_data, env):
    """
    Loads a Jinja2 template and renders it with provided data.

    Args:
        template_name (str): The name of the template file (e.g., 'email_with_list.html').
        context_data (dict): A dictionary of data to pass to the template.

    Returns:
        str: The rendered HTML content.
    """
    template = env.get_template(template_name)
    return template.render(context_data)

def main():

    file_path = "inventory.json"

    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(script_dir, 'templates') # Path to the templates folder

    # Configure Jinja2 to look for templates in the 'templates' subdirectory
    env = Environment(loader=FileSystemLoader(template_dir))

    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file) # This is the core function

        recipient_name = "team"
        greeting_message = f"Hello {recipient_name}"

        email_items = findDeletedTenants(data)
        email_subject = "Your Service Update Notification"

        # Data dictionary to pass to the Jinja2 template
        template_context = {
            "greeting_text": greeting_message,
            "items": email_items,
            "subject": email_subject # Subject can also be passed for template title
        }

        # Render the HTML body using Jinja2
        html_email_body = render_email_template('email.html', template_context, env)

        # Configuration - Replace with your details
        SENDER_EMAIL = "sradzhabov@meshcloud.io"
        APP_PASSWORD = "dkzl bokd koma stxl"
        RECIPIENT = "shamil.radzhabov@gmail.com"
        
        mail_client.send_email(
            sender_email=SENDER_EMAIL,
            app_password=APP_PASSWORD,
            to_email=RECIPIENT,
            subject=email_subject,
            body=html_email_body,
            is_html=True
        )

        #print(html_email_body)

#        for item in data:
#            print(f"Tencent account id: {item["localId"]}. meshStack tenant ID: {item["tenantIdentifier"]}")

if __name__ == "__main__":
    main()