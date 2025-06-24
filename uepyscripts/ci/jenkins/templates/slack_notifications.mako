<%def name="try_send_message(message_options, type='SlackNotificationMessageConfig')">
    % if message_options.enabled:
        sendMessageToSlack( "${message_options.message_template}", "${message_options.message_color}" )
    % endif
</%def>

<%def name="libraries()">
@Library('slack-notifier@master')
</%def>

<%def name="pre_build_steps()">
${try_send_message(message_options=feature_config.pre_build_step)}
</%def>

<%def name="on_build_failure()">
${try_send_message(message_options=feature_config.on_failure)}
</%def>

<%def name="on_build_unstable()">
${try_send_message(message_options=feature_config.on_unstable)}
</%def>

<%def name="on_build_success()">
${try_send_message(message_options=feature_config.on_success)}
</%def>

<%def name="on_exception_thrown()">
${try_send_message(message_options=feature_config.on_exception)}
</%def>

<%def name="additional_functions()">
def sendMessageToSlack( String message, String color ) {
    ${feature_config.message_template}
    slackSend channel: '${feature_config.channel}', color: color, message: full_message
}
</%def>