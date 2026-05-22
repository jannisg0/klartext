import ChatWindow from './components/ChatWindow.jsx'
import DevToggle from './components/DevToggle.jsx'
import Sidebar from './components/Sidebar.jsx'

export default function App() {
  return (
    <div className="dark min-h-screen bg-graphite text-bone">
      <div className="max-w-[1440px] mx-auto p-4">
        <div className="relative grain h-[calc(100vh-2rem)] rounded-xl overflow-hidden border border-edge bg-graphite grid grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)_380px]">
          <Sidebar />
          <ChatWindow />
        </div>
      </div>
      <DevToggle />
    </div>
  )
}
