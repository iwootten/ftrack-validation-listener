import ftrack_api
import logging

logging.basicConfig()


def submit_handler(event, session):
    """
    Handler for the form submission from a user
    :param event:
    :param session:
    :return:
    """
    if 'values' in event['data']:
        values = event['data']['values']

        entity_type = 'Task' if values['entityType'] == 'task' else 'AssetVersion'

        entity = session.get(entity_type, values['entityId'])

        # Force update to fire event on empty submission
        if not values['description']:
            entity['description'] = 'Empty'
            session.commit()
            entity['description'] = ''
            session.commit()
        else:
            user_id = event['source']['user']['id']

            entity['description'] = values['description']

            session.commit()

            update_notification = ftrack_api.event.base.Event(
                topic='ftrack.action.trigger-user-interface',
                data={
                    'type': 'message',
                    'success': True,
                    'message': 'Description added to entity.'
                },
                target=(
                    'applicationId=ftrack.client.web and user.id={0}'.format(user_id)
                )
            )

            session.event_hub.publish(update_notification)


def validation_listener(event, session):
    """
    Listener responding to approval events
    :param event:
    :param session:
    :return:
    """
    data = event['data']
    entities = data.get('entities', [])

    approved_status_id = session.query("Status where name is 'Approved'").one()['id']

    for entity_item in entities:

        if entity_item['entityType'] == 'task' or entity_item['entityType'] == 'assetversion':
            user_id = event['source']['user']['id']

            entity_type = 'Task' if entity_item['entityType'] == 'task' else 'AssetVersion'

            entity = session.get(entity_type, entity_item['entityId'])

            status_updated_no_description = 'changes' in entity_item and 'statusid' in entity_item['changes'] \
                                            and 'new' in entity_item['changes']['statusid'] \
                                            and entity_item['changes']['statusid']['new'] == approved_status_id \
                                            and not entity['description']

            approved_and_description_removed = 'changes' in entity_item and 'description' in entity_item['changes'] \
                                               and 'new' in entity_item['changes']['description'] \
                                               and not entity_item['changes']['description']['new'] \
                                               and entity['status_id'] == approved_status_id

            if status_updated_no_description or approved_and_description_removed:
                event = ftrack_api.event.base.Event(
                    topic='ftrack.action.trigger-user-interface',
                    data={
                        'actionIdentifier': 'validate-description',
                        'type': 'form',
                        'items': [
                            {
                                'value': "The entity '{}' has been marked as approved "
                                         "and requires a description".format(entity['name']),
                                'type': 'label'
                            },
                            {
                                'label': 'Description',
                                'name': 'description',
                                'type': 'text',
                            },
                            {
                                'type': 'hidden',
                                'name': 'entityId',
                                'value': entity_item['entityId']
                            },
                            {
                                'type': 'hidden',
                                'name': 'entityType',
                                'value': entity_item['entityType']
                            }
                        ],
                        'title': "Please add a description to '{}'".format(entity['name'])
                    },
                    target=(
                        'applicationId=ftrack.client.web and user.id={0}'.format(user_id)
                    )
                )

                session.event_hub.publish(event)


if __name__ == "__main__":
    ftrack_session = ftrack_api.Session(auto_connect_event_hub=True)
    ftrack_session.event_hub.subscribe('topic=ftrack.update and source.applicationId=ftrack.client.web',
                                       lambda event: validation_listener(event, ftrack_session))
    ftrack_session.event_hub.subscribe('topic=ftrack.action.launch and data.actionIdentifier=validate-description',
                                       lambda event: submit_handler(event, ftrack_session))
    ftrack_session.event_hub.wait()
