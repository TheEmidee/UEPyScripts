<%def name="try_send_message(event, type='SlackNotificationEventConfig')">
    % if event.simple_message.enabled:
        <%
            channel_override = event.simple_message.channel_override
            if channel_override.strip():
                channel_override = f', "{channel_override}"'
        %>
        sendMessageToSlack( "${event.simple_message.message_template}", "${event.simple_message.color}" ${channel_override} )
    % endif

    % if event.blocks_message.enabled:
        BLOCKS
    % endif
</%def>

<%def name="libraries()">
@Library('slack-notifier@master')
</%def>

<%def name="pre_build_steps()">
${try_send_message(event=feature_config.pre_build_step)}
</%def>

<%def name="on_build_failure()">
${try_send_message(event=feature_config.on_failure)}
</%def>

<%def name="on_build_unstable()">
${try_send_message(event=feature_config.on_unstable)}
</%def>

<%def name="on_build_success()">
${try_send_message(event=feature_config.on_success)}
</%def>

<%def name="on_exception_thrown()">
${try_send_message(event=feature_config.on_exception)}
</%def>

<%def name="additional_functions()">
def sendMessageToSlack( String message, String color, String channel = "${feature_config.channel}" ) {
    ${feature_config.message_template}
    slackSend channel: channel, color: color, message: full_message
}
</%def>