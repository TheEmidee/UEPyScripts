<%def name="libraries()">
@Library('slack-notifier@master')
</%def>

<%def name="on_build_failure()">
% if feature_config['on_failure']:
sendMessageToSlack( "Failed", "${feature_config['on_failure']['message_color']}" )
% endif
</%def>

<%def name="on_build_unstable()">
% if feature_config['on_unstable']:
sendMessageToSlack( "Unstable", "${feature_config['on_unstable']['message_color']}" )
% endif
</%def>

<%def name="on_build_success()">
% if feature_config['on_success']:
sendMessageToSlack( "Success", "${feature_config['on_success']['message_color']}" )
% endif
</%def>

<%def name="on_exception_thrown()">
% if feature_config['on_exception']:
sendMessageToSlack( "Failure", "${feature_config['on_exception']['message_color']}", "Reason : " + err.toString() )
% endif
</%def>

<%def name="additional_functions()">
def sendMessageToSlack( String message, String color, String suffix = "" ) {
    ${feature_config['message_template']}
    <%text>
    if ( !( suffix?.trim() ) ) {
        full_message += " " + suffix
    }
    </%text>

    slackSend channel: '${feature_config['channel']}', color: color, message: full_message
}
</%def>